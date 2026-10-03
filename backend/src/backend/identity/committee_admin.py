"""Operator-only, transactional committee bootstrap and lifecycle operations."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

from backend.errors import TransactionConflictError, TransactionUnavailableError
from backend.identity.errors import AdminOperationError
from backend.identity.validation import EMAIL_PATTERN

INVITATION_TTL = timedelta(hours=24)
IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
MEMBER_STATUSES = frozenset({"ordinary", "deputy"})
REPRESENTING_SIDES = frozenset({"employer", "employee", "school"})
PLACEHOLDERS = frozenset({"-", "n/a", "nicht konfiguriert", "not configured", "tbd", "todo"})
PersonMode = Literal["existing", "new"]


class CommitteeAdminUnitOfWork(Protocol):
    """Storage operations needed by Identity's committee admin use cases."""

    def begin_write(self) -> None: ...
    def flush(self) -> None: ...
    def create_committee(self, values: Mapping[str, Any]) -> CommitteeRecord: ...
    def get_committee(self, committee_id: int) -> CommitteeRecord | None: ...
    def save_committee(self, committee: CommitteeRecord) -> None: ...
    def delete_committee(self, committee_id: int) -> bool: ...
    def require_committee_manager(
        self,
        committee_id: int,
        actor_memberships: Mapping[int, int],
        actor_person_id: int | None,
    ) -> None: ...
    def person_by_email(self, email: str) -> PersonRecord | None: ...
    def account_by_email(self, email: str) -> AccountRecord | None: ...
    def account_by_person(self, person_id: int) -> AccountRecord | None: ...
    def create_person(self, values: Mapping[str, Any]) -> PersonRecord: ...
    def create_account(self, values: Mapping[str, Any]) -> AccountRecord: ...
    def membership_for_person(
        self, committee_id: int, person_id: int
    ) -> MembershipRecord | None: ...
    def active_membership_for_person(
        self, committee_id: int, person_id: int
    ) -> MembershipRecord | None: ...
    def create_membership(self, values: Mapping[str, Any]) -> MembershipRecord: ...
    def save_membership(self, membership: MembershipRecord) -> None: ...
    def active_memberships(self, committee_id: int) -> list[MembershipRecord]: ...
    def accounts_for_people(self, person_ids: list[int]) -> list[AccountRecord]: ...
    def count_active_role(self, committee_id: int, role: str) -> int: ...
    def open_invitations(self, account_id: int) -> list[InvitationRecord]: ...
    def consume_open_invitations(self, account_id: int, consumed_at: str) -> None: ...
    def create_invitation(self, values: Mapping[str, Any]) -> None: ...
    def operation_by_key(self, key: str) -> OperationRecord | None: ...
    def create_operation(self, values: Mapping[str, Any]) -> OperationRecord: ...


class CommitteeRecord(Protocol):
    id: int
    name: str
    occupation: str
    ihk: str
    is_active: int
    bootstrap_state: str
    created_at: str
    updated_at: str


class PersonRecord(Protocol):
    id: int
    email: str


class AccountRecord(Protocol):
    id: int
    is_operator: int
    is_active: int
    password_hash: str | None
    last_login_at: str | None
    totp_secret_encrypted: str | None
    passkey_enabled: int
    two_factor_enabled: int
    totp_enabled: int


class MembershipRecord(Protocol):
    id: int
    person_id: int
    committee_id: int
    is_active: int
    committee_role: str
    member_status: str
    representing_side: str
    updated_at: str


class InvitationRecord(Protocol):
    expires_at: str


class OperationRecord(Protocol):
    id: int
    request_hash: str
    response_json: str | None


class CommitteeAdminUnitOfWorkFactory(Protocol):
    """Open isolated committee admin read snapshots and write transactions."""

    def snapshot(self) -> AbstractContextManager[CommitteeAdminUnitOfWork]: ...
    def unit_of_work(self) -> AbstractContextManager[CommitteeAdminUnitOfWork]: ...


@dataclass(frozen=True)
class PersonSelection:
    """Validated person and membership input without client-controlled role fields."""

    mode: PersonMode
    email: str
    member_status: str
    representing_side: str
    first_name: str | None = None
    last_name: str | None = None
    mobile: str | None = None

    def canonical(self) -> dict[str, object]:
        result: dict[str, object] = {
            "mode": self.mode,
            "email": self.email,
            "member_status": self.member_status,
            "representing_side": self.representing_side,
        }
        if self.mode == "new":
            result.update(
                {
                    "first_name": self.first_name,
                    "last_name": self.last_name,
                    "mobile": self.mobile,
                }
            )
        return result


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _now(value).isoformat(timespec="seconds")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_hash(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _mapping(value: object, message: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdminOperationError("invalid_request", message)
    return value


def _strict_keys(
    value: Mapping[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    keys = frozenset(value)
    if not required.issubset(keys) or not keys.issubset(required | optional):
        raise AdminOperationError("invalid_request", "Admin arguments do not match the contract")


def _text(value: object, field: str, *, maximum: int = 200) -> str:
    if not isinstance(value, str):
        raise AdminOperationError("invalid_request", f"Argument {field} is required")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise AdminOperationError("invalid_request", f"Argument {field} is invalid")
    return normalized


def _email(value: object) -> str:
    normalized = _text(value, "email", maximum=254).lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise AdminOperationError("invalid_request", "A valid person email is required")
    return normalized


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdminOperationError("invalid_request", f"Argument {field} must be positive")
    return value


def _idempotency_key(value: object) -> str:
    if not isinstance(value, str) or IDEMPOTENCY_KEY_PATTERN.fullmatch(value) is None:
        raise AdminOperationError(
            "invalid_request", "A valid idempotency key of 8 to 128 characters is required"
        )
    return value


def _person_selection(value: object) -> PersonSelection:
    raw = _mapping(value, "Person selection must be an object")
    mode = raw.get("mode")
    if mode == "existing":
        _strict_keys(
            raw,
            required=frozenset({"mode", "email", "member_status", "representing_side"}),
        )
    elif mode == "new":
        _strict_keys(
            raw,
            required=frozenset(
                {
                    "mode",
                    "email",
                    "first_name",
                    "last_name",
                    "member_status",
                    "representing_side",
                }
            ),
            optional=frozenset({"mobile"}),
        )
    else:
        raise AdminOperationError("invalid_request", "Person mode must be existing or new")

    member_status = raw.get("member_status")
    representing_side = raw.get("representing_side")
    if member_status not in MEMBER_STATUSES:
        raise AdminOperationError("invalid_request", "Unknown member status")
    if representing_side not in REPRESENTING_SIDES:
        raise AdminOperationError("invalid_request", "Unknown representing side")

    first_name = _text(raw.get("first_name"), "first_name") if mode == "new" else None
    last_name = _text(raw.get("last_name"), "last_name") if mode == "new" else None
    mobile_value = raw.get("mobile")
    mobile = None
    if mode == "new" and mobile_value not in (None, ""):
        mobile = _text(mobile_value, "mobile", maximum=80)
    return PersonSelection(
        mode=mode,
        email=_email(raw.get("email")),
        member_status=str(member_status),
        representing_side=str(representing_side),
        first_name=first_name,
        last_name=last_name,
        mobile=mobile,
    )


class CommitteeAdminService:
    """Local operator boundary for committee bootstrap and lifecycle writes."""

    def __init__(self, unit_of_work_factory: CommitteeAdminUnitOfWorkFactory):
        self.unit_of_work_factory = unit_of_work_factory

    def update_master_data(
        self,
        committee_id: int,
        values: Mapping[str, Any],
        *,
        actor_memberships: Mapping[int, int],
        actor_person_id: int | None,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Update committee master data inside an authorized Identity UoW."""
        with self.unit_of_work_factory.unit_of_work() as session:
            session.begin_write()
            session.require_committee_manager(committee_id, actor_memberships, actor_person_id)
            committee = session.get_committee(committee_id)
            if committee is None:
                return None
            for field in ("name", "occupation", "ihk"):
                if field in values:
                    setattr(committee, field, values[field])
            committee.updated_at = _timestamp(_now(now))
            session.save_committee(committee)
            return self._committee_view(committee)

    def delete_master_data(
        self,
        committee_id: int,
        *,
        actor_memberships: Mapping[int, int],
        actor_person_id: int | None,
    ) -> bool:
        """Delete a committee through the Identity-owned transaction boundary."""
        with self.unit_of_work_factory.unit_of_work() as session:
            session.begin_write()
            session.require_committee_manager(committee_id, actor_memberships, actor_person_id)
            return session.delete_committee(committee_id)

    @staticmethod
    def _committee_view(committee: CommitteeRecord) -> dict[str, Any]:
        return {
            "id": committee.id,
            "name": committee.name,
            "occupation": committee.occupation,
            "ihk": committee.ihk,
            "is_active": committee.is_active,
            "bootstrap_state": committee.bootstrap_state,
            "created_at": committee.created_at,
            "updated_at": committee.updated_at,
        }

    def bootstrap(
        self, arguments: Mapping[str, Any], *, now: datetime | None = None
    ) -> dict[str, Any]:
        _strict_keys(
            arguments,
            required=frozenset({"idempotency_key", "committee", "chair"}),
            optional=frozenset({"deputy"}),
        )
        key = _idempotency_key(arguments.get("idempotency_key"))
        committee_raw = _mapping(arguments.get("committee"), "Committee must be an object")
        _strict_keys(
            committee_raw,
            required=frozenset({"name", "ihk", "occupation"}),
        )
        committee_data = {
            field: self._committee_text(committee_raw.get(field), field)
            for field in ("name", "ihk", "occupation")
        }
        chair = _person_selection(arguments.get("chair"))
        deputy = (
            _person_selection(arguments.get("deputy"))
            if arguments.get("deputy") is not None
            else None
        )
        canonical = {
            "operation": "bootstrap",
            "committee": committee_data,
            "chair": chair.canonical(),
            "deputy": deputy.canonical() if deputy else None,
        }
        digest = _request_hash(canonical)
        replay = self._existing_replay(key, digest)
        if replay is not None:
            return replay

        current = _now(now)
        try:
            with self.unit_of_work_factory.unit_of_work() as session:
                session.begin_write()
                replay = self._replay_in_session(session, key, digest)
                if replay is not None:
                    return replay
                committee = session.create_committee(
                    {
                        **committee_data,
                        "is_active": 1,
                        "bootstrap_state": "needs_clarification",
                        "created_at": _timestamp(current),
                        "updated_at": _timestamp(current),
                    }
                )
                return self._assign_leadership(
                    session,
                    operation="bootstrap",
                    committee=committee,
                    chair=chair,
                    deputy=deputy,
                    key=key,
                    digest=digest,
                    current=current,
                    allow_incomplete_membership=False,
                )
        except TransactionConflictError as error:
            replay = self._existing_replay(key, digest)
            if replay is not None:
                return replay
            raise AdminOperationError(
                "committee_conflict", "Committee bootstrap conflicts with existing data"
            ) from error
        except TransactionUnavailableError as error:
            raise AdminOperationError(
                "persistence_error", "Committee bootstrap could not be completed"
            ) from error

    def complete(
        self, arguments: Mapping[str, Any], *, now: datetime | None = None
    ) -> dict[str, Any]:
        _strict_keys(
            arguments,
            required=frozenset({"idempotency_key", "committee_id", "chair"}),
            optional=frozenset({"deputy"}),
        )
        key = _idempotency_key(arguments.get("idempotency_key"))
        committee_id = _positive_integer(arguments.get("committee_id"), "committee_id")
        chair = _person_selection(arguments.get("chair"))
        deputy = (
            _person_selection(arguments.get("deputy"))
            if arguments.get("deputy") is not None
            else None
        )
        canonical = {
            "operation": "complete",
            "committee_id": committee_id,
            "chair": chair.canonical(),
            "deputy": deputy.canonical() if deputy else None,
        }
        digest = _request_hash(canonical)
        replay = self._existing_replay(key, digest)
        if replay is not None:
            return replay

        current = _now(now)
        try:
            with self.unit_of_work_factory.unit_of_work() as session:
                session.begin_write()
                replay = self._replay_in_session(session, key, digest)
                if replay is not None:
                    return replay
                committee = session.get_committee(committee_id)
                if committee is None:
                    raise AdminOperationError("committee_not_found", "Committee was not found")
                active_chairs = self._active_role_count(session, committee.id, "chair")
                if (
                    not committee.is_active
                    or committee.bootstrap_state != "needs_clarification"
                    or active_chairs != 0
                ):
                    raise AdminOperationError(
                        "committee_conflict", "Committee cannot be completed administratively"
                    )
                return self._assign_leadership(
                    session,
                    operation="complete",
                    committee=committee,
                    chair=chair,
                    deputy=deputy,
                    key=key,
                    digest=digest,
                    current=current,
                    allow_incomplete_membership=True,
                )
        except AdminOperationError:
            raise
        except TransactionConflictError as error:
            replay = self._existing_replay(key, digest)
            if replay is not None:
                return replay
            raise AdminOperationError(
                "committee_conflict", "Committee completion conflicts with existing data"
            ) from error
        except TransactionUnavailableError as error:
            raise AdminOperationError(
                "persistence_error", "Committee completion could not be completed"
            ) from error

    def reinvite(
        self, arguments: Mapping[str, Any], *, now: datetime | None = None
    ) -> dict[str, Any]:
        _strict_keys(
            arguments,
            required=frozenset({"idempotency_key", "committee_id", "email"}),
        )
        key = _idempotency_key(arguments.get("idempotency_key"))
        committee_id = _positive_integer(arguments.get("committee_id"), "committee_id")
        email = _email(arguments.get("email"))
        canonical = {
            "operation": "reinvite",
            "committee_id": committee_id,
            "email": email,
        }
        digest = _request_hash(canonical)
        replay = self._existing_replay(key, digest)
        if replay is not None:
            return replay

        current = _now(now)
        current_timestamp = _timestamp(current)
        try:
            with self.unit_of_work_factory.unit_of_work() as session:
                session.begin_write()
                replay = self._replay_in_session(session, key, digest)
                if replay is not None:
                    return replay
                committee, person, membership, account = self._reinvitation_target(
                    session, committee_id, email, current_timestamp
                )
                session.consume_open_invitations(account.id, current_timestamp)
                invitation = self._issue_invitation(session, account, current)
                return self._record_result(
                    session,
                    operation="reinvite",
                    committee=committee,
                    person_ids=[person.id],
                    membership_ids=[membership.id],
                    account_ids=[account.id],
                    invitations=[invitation],
                    key=key,
                    digest=digest,
                    current=current,
                )
        except AdminOperationError:
            raise
        except TransactionConflictError as error:
            replay = self._existing_replay(key, digest)
            if replay is not None:
                return replay
            raise AdminOperationError(
                "invitation_not_eligible", "Invitation cannot be reissued"
            ) from error

    def _reinvitation_target(
        self,
        session: CommitteeAdminUnitOfWork,
        committee_id: int,
        email: str,
        current_timestamp: str,
    ) -> tuple[CommitteeRecord, PersonRecord, MembershipRecord, AccountRecord]:
        """Resolve and validate eligibility before invalidating or issuing tokens."""
        committee = session.get_committee(committee_id)
        if committee is None or not committee.is_active or committee.bootstrap_state != "ready":
            raise AdminOperationError("committee_not_found", "Active committee was not found")
        person = self._person_by_email(session, email)
        if person is None:
            raise AdminOperationError("invitation_not_eligible", "Invitation cannot be reissued")
        membership = session.active_membership_for_person(committee_id, person.id)
        if membership is None:
            raise AdminOperationError("invitation_not_eligible", "Invitation cannot be reissued")
        account = self._linked_account(session, person)
        if account is None or not self._never_activated(account):
            raise AdminOperationError("invitation_not_eligible", "Invitation cannot be reissued")
        open_tokens = session.open_invitations(account.id)
        if not open_tokens or any(token.expires_at > current_timestamp for token in open_tokens):
            raise AdminOperationError("invitation_not_eligible", "Invitation cannot be reissued")
        return committee, person, membership, account

    def deactivate(
        self, arguments: Mapping[str, Any], *, now: datetime | None = None
    ) -> dict[str, Any]:
        return self._lifecycle(arguments, activate=False, now=now)

    def reactivate(
        self, arguments: Mapping[str, Any], *, now: datetime | None = None
    ) -> dict[str, Any]:
        return self._lifecycle(arguments, activate=True, now=now)

    def _lifecycle(
        self,
        arguments: Mapping[str, Any],
        *,
        activate: bool,
        now: datetime | None,
    ) -> dict[str, Any]:
        _strict_keys(
            arguments,
            required=frozenset({"idempotency_key", "committee_id", "reason"}),
        )
        operation = "reactivate" if activate else "deactivate"
        key = _idempotency_key(arguments.get("idempotency_key"))
        committee_id = _positive_integer(arguments.get("committee_id"), "committee_id")
        reason = _text(arguments.get("reason"), "reason", maximum=1000)
        canonical = {
            "operation": operation,
            "committee_id": committee_id,
            "reason": reason,
        }
        digest = _request_hash(canonical)
        replay = self._existing_replay(key, digest)
        if replay is not None:
            return replay

        current = _now(now)
        try:
            with self.unit_of_work_factory.unit_of_work() as session:
                session.begin_write()
                replay = self._replay_in_session(session, key, digest)
                if replay is not None:
                    return replay
                committee = session.get_committee(committee_id)
                if committee is None:
                    raise AdminOperationError("committee_not_found", "Committee was not found")
                if bool(committee.is_active) == activate:
                    raise AdminOperationError(
                        "committee_conflict", "Committee lifecycle state conflicts"
                    )
                if activate and (
                    committee.bootstrap_state != "ready"
                    or self._active_role_count(session, committee.id, "chair") != 1
                ):
                    raise AdminOperationError(
                        "committee_conflict", "Committee cannot be reactivated"
                    )
                committee.is_active = int(activate)
                committee.updated_at = _timestamp(current)
                session.save_committee(committee)
                memberships = session.active_memberships(committee.id)
                person_ids = [membership.person_id for membership in memberships]
                account_ids = [account.id for account in session.accounts_for_people(person_ids)]
                return self._record_result(
                    session,
                    operation=operation,
                    committee=committee,
                    person_ids=person_ids,
                    membership_ids=[membership.id for membership in memberships],
                    account_ids=account_ids,
                    invitations=[],
                    key=key,
                    digest=digest,
                    current=current,
                    reason=reason,
                )
        except AdminOperationError:
            raise
        except TransactionConflictError as error:
            replay = self._existing_replay(key, digest)
            if replay is not None:
                return replay
            raise AdminOperationError(
                "committee_conflict", "Committee lifecycle state conflicts"
            ) from error

    def _assign_leadership(
        self,
        session: CommitteeAdminUnitOfWork,
        *,
        operation: str,
        committee: CommitteeRecord,
        chair: PersonSelection,
        deputy: PersonSelection | None,
        key: str,
        digest: str,
        current: datetime,
        allow_incomplete_membership: bool,
    ) -> dict[str, Any]:
        chair_person = self._resolve_person(session, chair, current)
        deputy_person = self._resolve_person(session, deputy, current) if deputy else None
        if deputy_person is not None and deputy_person.id == chair_person.id:
            raise AdminOperationError(
                "person_conflict", "Chair and deputy chair must be different people"
            )

        people = [chair_person, *([deputy_person] if deputy_person else [])]
        invitations: list[dict[str, object]] = []
        accounts: list[AccountRecord] = []
        for person in people:
            account, invitation = self._account_for_person(session, person, current)
            accounts.append(account)
            if invitation is not None:
                invitations.append(invitation)

        memberships = [
            self._membership(
                session,
                committee,
                chair_person,
                chair,
                "chair",
                current,
                allow_incomplete=allow_incomplete_membership,
            )
        ]
        if deputy is not None and deputy_person is not None:
            memberships.append(
                self._membership(
                    session,
                    committee,
                    deputy_person,
                    deputy,
                    "deputy_chair",
                    current,
                    allow_incomplete=allow_incomplete_membership,
                )
            )
        committee.bootstrap_state = "ready"
        committee.updated_at = _timestamp(current)
        session.save_committee(committee)
        session.flush()
        if self._active_role_count(session, committee.id, "chair") != 1:
            raise AdminOperationError(
                "committee_conflict", "Committee requires exactly one active chair"
            )
        return self._record_result(
            session,
            operation=operation,
            committee=committee,
            person_ids=[person.id for person in people],
            membership_ids=[membership.id for membership in memberships],
            account_ids=[account.id for account in accounts],
            invitations=invitations,
            key=key,
            digest=digest,
            current=current,
        )

    def _resolve_person(
        self, session: CommitteeAdminUnitOfWork, selection: PersonSelection, current: datetime
    ) -> PersonRecord:
        existing = self._person_by_email(session, selection.email)
        account_with_email = session.account_by_email(selection.email)
        if selection.mode == "existing":
            if existing is None:
                raise AdminOperationError("person_not_found", "Existing person was not found")
            return existing
        if existing is not None or account_with_email is not None:
            raise AdminOperationError(
                "person_conflict", "Person already exists; use the explicit reuse path"
            )
        person = session.create_person(
            {
                "first_name": selection.first_name or "",
                "last_name": selection.last_name or "",
                "email": selection.email,
                "mobile": selection.mobile,
                "created_at": _timestamp(current),
                "updated_at": _timestamp(current),
            }
        )
        return person

    def _account_for_person(
        self, session: CommitteeAdminUnitOfWork, person: PersonRecord, current: datetime
    ) -> tuple[AccountRecord, dict[str, object] | None]:
        account = self._linked_account(session, person, required=False)
        account_with_email = session.account_by_email(person.email.lower())
        if account is not None:
            if account_with_email is not None and account_with_email.id != account.id:
                raise AdminOperationError(
                    "account_conflict", "A conflicting account requires clarification"
                )
            return account, None
        if account_with_email is not None:
            raise AdminOperationError(
                "account_conflict", "A conflicting account requires clarification"
            )
        account = session.create_account(
            {
                "person_id": person.id,
                "email": person.email.lower(),
                "is_operator": 0,
                "is_active": 1,
                "created_at": _timestamp(current),
                "updated_at": _timestamp(current),
            }
        )
        return account, self._issue_invitation(session, account, current)

    def _linked_account(
        self, session: CommitteeAdminUnitOfWork, person: PersonRecord, *, required: bool = True
    ) -> AccountRecord | None:
        account = session.account_by_person(person.id)
        if account is None:
            if required:
                raise AdminOperationError(
                    "account_conflict", "A linked active account was not found"
                )
            return None
        if account.is_operator or not account.is_active:
            raise AdminOperationError(
                "account_conflict", "A conflicting account requires clarification"
            )
        return account

    def _membership(
        self,
        session: CommitteeAdminUnitOfWork,
        committee: CommitteeRecord,
        person: PersonRecord,
        selection: PersonSelection,
        role: str,
        current: datetime,
        *,
        allow_incomplete: bool,
    ) -> MembershipRecord:
        existing = session.membership_for_person(committee.id, person.id)
        if existing is not None:
            exact_incomplete = (
                allow_incomplete
                and not existing.is_active
                and existing.committee_role == role
                and existing.member_status == selection.member_status
                and existing.representing_side == selection.representing_side
            )
            if not exact_incomplete:
                raise AdminOperationError(
                    "membership_conflict", "Existing membership requires clarification"
                )
            existing.is_active = 1
            existing.updated_at = _timestamp(current)
            session.save_membership(existing)
            return existing
        return session.create_membership(
            {
                "person_id": person.id,
                "committee_id": committee.id,
                "member_status": selection.member_status,
                "committee_role": role,
                "representing_side": selection.representing_side,
                "is_active": 1,
                "created_at": _timestamp(current),
                "updated_at": _timestamp(current),
            }
        )

    @staticmethod
    def _issue_invitation(
        session: CommitteeAdminUnitOfWork, account: AccountRecord, current: datetime
    ) -> dict[str, object]:
        token = secrets.token_urlsafe(32)
        expires_at = _timestamp(current + INVITATION_TTL)
        session.create_invitation(
            {
                "account_id": account.id,
                "kind": "invitation",
                "token_hash": _token_hash(token),
                "created_at": _timestamp(current),
                "expires_at": expires_at,
            }
        )
        return {"account_id": account.id, "expires_at": expires_at, "token": token}

    def _record_result(
        self,
        session: CommitteeAdminUnitOfWork,
        *,
        operation: str,
        committee: CommitteeRecord,
        person_ids: list[int],
        membership_ids: list[int],
        account_ids: list[int],
        invitations: list[dict[str, object]],
        key: str,
        digest: str,
        current: datetime,
        reason: str | None = None,
    ) -> dict[str, Any]:
        person_ids = list(dict.fromkeys(person_ids))
        membership_ids = list(dict.fromkeys(membership_ids))
        account_ids = list(dict.fromkeys(account_ids))
        base_result: dict[str, Any] = {
            "operation": operation,
            "committee_id": committee.id,
            "is_active": bool(committee.is_active),
            "bootstrap_state": committee.bootstrap_state,
            "person_ids": person_ids,
            "membership_ids": membership_ids,
            "account_ids": account_ids,
            "invitations_issued": len(invitations),
            "replayed": False,
        }
        evidence = session.create_operation(
            {
                "operation_type": operation,
                "committee_id": committee.id,
                "person_ids_json": _canonical_json(person_ids),
                "membership_ids_json": _canonical_json(membership_ids),
                "account_ids_json": _canonical_json(account_ids),
                "result": "succeeded",
                "occurred_at": _timestamp(current),
                "technical_source": "operator-cli",
                "idempotency_key": key,
                "request_hash": digest,
                "reason": reason,
                "response_json": _canonical_json(base_result),
            }
        )
        result = dict(base_result)
        result["evidence_id"] = evidence.id
        result["invitations"] = invitations
        return result

    def _existing_replay(self, key: str, digest: str) -> dict[str, Any] | None:
        with self.unit_of_work_factory.snapshot() as session:
            return self._replay_in_session(session, key, digest)

    @staticmethod
    def _replay_in_session(
        session: CommitteeAdminUnitOfWork, key: str, digest: str
    ) -> dict[str, Any] | None:
        operation = session.operation_by_key(key)
        if operation is None:
            return None
        if operation.request_hash != digest:
            raise AdminOperationError(
                "idempotency_conflict", "Idempotency key was used with different input"
            )
        if operation.response_json is None:
            raise AdminOperationError("persistence_error", "Stored operation is incomplete")
        result = json.loads(operation.response_json)
        result["evidence_id"] = operation.id
        result["replayed"] = True
        result["invitations"] = []
        return result

    @staticmethod
    def _person_by_email(session: CommitteeAdminUnitOfWork, email: str) -> PersonRecord | None:
        return session.person_by_email(email)

    @staticmethod
    def _active_role_count(session: CommitteeAdminUnitOfWork, committee_id: int, role: str) -> int:
        return session.count_active_role(committee_id, role)

    @staticmethod
    def _never_activated(account: AccountRecord) -> bool:
        return (
            account.password_hash is None
            and account.last_login_at is None
            and account.totp_secret_encrypted is None
            and not account.passkey_enabled
            and not account.two_factor_enabled
            and not account.totp_enabled
        )

    @staticmethod
    def _committee_text(value: object, field: str) -> str:
        normalized = _text(value, field)
        if normalized.casefold() in PLACEHOLDERS:
            raise AdminOperationError("invalid_request", f"Argument {field} is a placeholder")
        return normalized
