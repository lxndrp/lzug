"""SQLite persistence adapter for the Planning-owned venue port.

This module deliberately keeps the venue aggregate outside the generic resource
repository.  Venue, room, and contact updates have optimistic revisions,
append-only audit records, and cross-entity invariants that do not belong in
generic CRUD helpers.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from contextlib import contextmanager, nullcontext
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.persistence.database import DEFAULT_DB_PATH, session_scope
from backend.persistence.models import (
    EXAM_ROOM,
    EXAM_VENUE,
    EXAM_VENUE_CONTACT,
    Committee,
    CommitteeMember,
    ExamDay,
    ExamDayAssignment,
    ExamRoom,
    ExamRound,
    ExamVenue,
    ExamVenueAuditEvent,
    ExamVenueContact,
    ExamVenueContactRoom,
    LegacyLocationRoomMapping,
    PlanningSettings,
    model_to_dict,
)
from backend.planning_ports import (
    CONTACT_FIELDS,
    ROOM_FIELDS,
    VENUE_DUPLICATE_FIELDS,
    VENUE_FIELDS,
    ExamVenueConflictError,
    ExamVenueError,
    ExamVenueInUseError,
    ExamVenueNotFoundError,
    VenueChange,
    VenueCommand,
    VenueCommandFacts,
    VenueCommandKind,
    VenueCommandResult,
    VenueCommandUnitOfWork,
    VenueFutureImpactFacts,
    VenueMutationPlan,
    VenueQuery,
    VenueQueryKind,
    VenueQueryResult,
    VenueRoomAvailability,
)
from backend.planning_ports import (
    room_is_usable_for_committee as decide_room_eligibility,
)


def room_is_usable_for_committee(
    session: Session,
    room_id: int,
    committee_id: int,
    *,
    require_confirmed_coordinates: bool = False,
) -> bool:
    """Return whether a room is active and selectable by this committee's new plan."""
    room = session.get(ExamRoom, room_id)
    venue = session.get(ExamVenue, room.venue_id) if room is not None else None
    availability = (
        VenueRoomAvailability(
            room_active=bool(room.is_active),
            venue_active=bool(venue.is_active),
            venue_scope=venue.scope,
            committee_id=venue.committee_id,
            coordinate_status=venue.coordinate_status,
        )
        if room is not None and venue is not None
        else None
    )
    return decide_room_eligibility(
        availability,
        committee_id,
        require_confirmed_coordinates=require_confirmed_coordinates,
    )


class _SQLiteVenueCommandUnitOfWork(VenueCommandUnitOfWork):
    def __init__(
        self,
        repository: SQLiteExamVenueRepository,
        session: Session,
        command: VenueCommand,
    ) -> None:
        self.repository = repository
        self.session = session
        self.command = command
        self._facts: VenueCommandFacts | None = None

    def facts(self) -> VenueCommandFacts:
        if self._facts is None:
            self._facts = self.repository._command_facts(self.session, self.command)
        return self._facts

    def commit(self, plan: VenueMutationPlan) -> VenueCommandResult:
        if self._facts is None:
            raise RuntimeError("Read command facts before committing a venue plan")
        return self.repository.execute(self.command, plan, session=self.session)


class SQLiteExamVenueRepository:
    """Create and mutate the venue aggregate in one transaction per command."""

    def __init__(
        self,
        db_path: Path = DEFAULT_DB_PATH,
        *,
        require_confirmed_coordinates: bool = False,
    ):
        self.db_path = Path(db_path)
        self.require_confirmed_coordinates = require_confirmed_coordinates

    @contextmanager
    def _write_session(self, session: Session | None):
        if session is None:
            with session_scope(self.db_path, begin_immediate=True) as owned_session:
                yield owned_session
        else:
            with nullcontext(session) as active_session:
                yield active_session

    def query(self, query: VenueQuery) -> VenueQueryResult:
        """Run one Planning venue query and return detached values."""
        return VenueQueryResult(self._query_value(query))

    def _query_value(self, query: VenueQuery) -> object:
        values = dict(query.values or {})
        match query.kind:
            case VenueQueryKind.LIST_VENUES:
                return self.list_venues()
            case VenueQueryKind.GET_VENUE:
                if query.entity_id is None:
                    raise ValueError("Venue query needs an entity id")
                return self.get_venue(query.entity_id)
            case VenueQueryKind.ADDRESS_LABEL:
                if query.entity_id is None:
                    raise ValueError("Address query needs a venue id")
                return self.address_label(query.entity_id)
            case VenueQueryKind.REFERENCED_COMMITTEES:
                if query.entity_id is None:
                    raise ValueError("Reference query needs a venue id")
                return self.referenced_committee_ids(query.entity_id)
            case VenueQueryKind.FUTURE_IMPACT:
                if query.entity_id is None:
                    raise ValueError("Impact query needs a venue id")
                return self.future_impact_facts(query.entity_id, query.room_id, values)
            case VenueQueryKind.FIND_DUPLICATES:
                return self.find_duplicate_candidates(
                    visible_venue_ids=query.visible_venue_ids,
                    excluded_id=query.excluded_id,
                )
            case VenueQueryKind.LIST_PENDING_PROMOTIONS:
                return self.list_pending_promotions()

    @contextmanager
    def write_uow(self, command: VenueCommand):
        """Open the command's serialized write transaction for Planning orchestration."""
        with session_scope(self.db_path, begin_immediate=True) as session:
            yield _SQLiteVenueCommandUnitOfWork(self, session, command)

    def _command_facts(self, session: Session, command: VenueCommand) -> VenueCommandFacts:
        self._require_actor(session, command.actor_member_id, command.technical_actor)
        kind = command.kind
        venue = None
        room = None
        contact = None
        if kind in {
            VenueCommandKind.CREATE_VENUE,
            VenueCommandKind.UPDATE_VENUE,
            VenueCommandKind.DELETE_VENUE,
            VenueCommandKind.REQUEST_PROMOTION,
            VenueCommandKind.DECIDE_PROMOTION,
        }:
            venue = session.get(ExamVenue, command.entity_id) if command.entity_id else None
            if venue is None and kind in {
                VenueCommandKind.REQUEST_PROMOTION,
                VenueCommandKind.DECIDE_PROMOTION,
            }:
                raise ExamVenueNotFoundError("Exam venue not found")
        elif kind in {
            VenueCommandKind.CREATE_ROOM,
            VenueCommandKind.CREATE_CONTACT,
        }:
            venue = session.get(ExamVenue, command.entity_id) if command.entity_id else None
            if venue is None:
                raise ExamVenueNotFoundError("Exam venue not found")
        elif kind in {VenueCommandKind.UPDATE_ROOM, VenueCommandKind.DELETE_ROOM}:
            room = session.get(ExamRoom, command.entity_id) if command.entity_id else None
            venue = session.get(ExamVenue, room.venue_id) if room is not None else None
        elif kind in {VenueCommandKind.UPDATE_CONTACT, VenueCommandKind.DELETE_CONTACT}:
            contact = (
                session.get(ExamVenueContact, command.entity_id) if command.entity_id else None
            )
            venue = session.get(ExamVenue, contact.venue_id) if contact is not None else None

        entity = (
            venue
            if kind
            in {
                VenueCommandKind.UPDATE_VENUE,
                VenueCommandKind.DELETE_VENUE,
                VenueCommandKind.REQUEST_PROMOTION,
                VenueCommandKind.DECIDE_PROMOTION,
            }
            else (
                room
                if kind
                in {
                    VenueCommandKind.UPDATE_ROOM,
                    VenueCommandKind.DELETE_ROOM,
                }
                else contact
            )
        )
        if entity is not None and command.expected_revision is not None:
            self._assert_revision(entity.revision, command.expected_revision)

        if kind in {VenueCommandKind.CREATE_VENUE, VenueCommandKind.UPDATE_VENUE}:
            current = (
                {field: getattr(venue, field) for field in VENUE_FIELDS}
                if venue is not None
                else None
            )
        elif kind in {VenueCommandKind.CREATE_ROOM, VenueCommandKind.UPDATE_ROOM}:
            current = (
                {field: getattr(room, field) for field in ROOM_FIELDS} if room is not None else None
            )
        elif kind == VenueCommandKind.UPDATE_CONTACT:
            current = (
                {field: getattr(contact, field) for field in CONTACT_FIELDS - {"room_ids"}}
                if contact is not None
                else None
            )
        elif kind in {VenueCommandKind.REQUEST_PROMOTION, VenueCommandKind.DECIDE_PROMOTION}:
            current = (
                {field: getattr(venue, field) for field in VENUE_FIELDS}
                if venue is not None
                else None
            )
        else:
            current = None

        venue_id = (
            venue.id
            if venue is not None
            else (
                command.entity_id
                if kind
                in {
                    VenueCommandKind.CREATE_VENUE,
                    VenueCommandKind.UPDATE_VENUE,
                    VenueCommandKind.DELETE_VENUE,
                    VenueCommandKind.REQUEST_PROMOTION,
                    VenueCommandKind.DECIDE_PROMOTION,
                    VenueCommandKind.CREATE_ROOM,
                    VenueCommandKind.CREATE_CONTACT,
                }
                else None
            )
        )
        has_active_room = bool(
            venue_id is not None
            and session.scalar(
                select(ExamRoom.id)
                .where(ExamRoom.venue_id == venue_id, ExamRoom.is_active == 1)
                .limit(1)
            )
        )
        other_active_room = bool(
            room is not None
            and session.scalar(
                select(ExamRoom.id)
                .where(
                    ExamRoom.venue_id == room.venue_id,
                    ExamRoom.id != room.id,
                    ExamRoom.is_active == 1,
                )
                .limit(1)
            )
        )
        values = dict(command.values or {})
        duplicate_candidates = None
        if kind in {VenueCommandKind.CREATE_VENUE, VenueCommandKind.UPDATE_VENUE} and (
            kind == VenueCommandKind.CREATE_VENUE or VENUE_DUPLICATE_FIELDS.intersection(values)
        ):
            duplicate_candidates = self._duplicate_candidates(
                session, excluded_id=venue.id if venue is not None else None
            )
        elif kind == VenueCommandKind.DECIDE_PROMOTION and command.decision == "approve":
            duplicate_candidates = self._duplicate_candidates(
                session, excluded_id=venue.id if venue is not None else None
            )

        has_future_assignments = None
        if kind == VenueCommandKind.UPDATE_VENUE and venue_id is not None:
            has_future_assignments = self._has_future_confirmed_assignments(session, venue_id)
        elif kind == VenueCommandKind.UPDATE_ROOM and room is not None:
            has_future_assignments = self._has_future_confirmed_assignments(
                session, room.venue_id, room.id
            )

        room_venue_ids = None
        if kind == VenueCommandKind.CREATE_CONTACT and "room_ids" in values:
            room_venue_ids = self._room_venue_ids(session, values.get("room_ids"))
        elif kind == VenueCommandKind.UPDATE_CONTACT and "room_ids" in values:
            room_venue_ids = self._room_venue_ids(session, values.get("room_ids"))

        return VenueCommandFacts(
            current=current,
            venue_id=venue_id,
            venue_active=bool(venue and venue.is_active),
            has_active_room=has_active_room,
            room_active=bool(room and room.is_active),
            has_another_active_room=other_active_room,
            promotion_status=(
                self._promotion_status(session, venue.id)
                if venue is not None
                and kind in {VenueCommandKind.REQUEST_PROMOTION, VenueCommandKind.DECIDE_PROMOTION}
                else None
            ),
            room_venue_ids=room_venue_ids,
            duplicate_candidates=duplicate_candidates,
            has_future_confirmed_assignments=has_future_assignments,
        )

    def execute(
        self, command: VenueCommand, plan: VenueMutationPlan, *, session: Session
    ) -> VenueCommandResult:
        """Persist a Planning-validated plan inside the active command UoW."""
        values = dict(command.values or {})
        match command.kind:
            case VenueCommandKind.CREATE_VENUE:
                value = self.create_venue(
                    values,
                    plan=plan,
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    _session=session,
                )
            case VenueCommandKind.UPDATE_VENUE:
                value, change = self._update_venue_with_change(
                    self._command_entity_id(command),
                    {**values, "expected_revision": command.expected_revision},
                    plan=plan,
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    _session=session,
                )
                return VenueCommandResult(value, change)
            case VenueCommandKind.DELETE_VENUE:
                value = self.delete_venue(
                    self._command_entity_id(command),
                    expected_revision=self._command_revision(command),
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    reason=command.reason,
                    _session=session,
                )
            case VenueCommandKind.CREATE_ROOM:
                value = self.create_room(
                    self._command_entity_id(command),
                    values,
                    plan=plan,
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    _session=session,
                )
            case VenueCommandKind.UPDATE_ROOM:
                value, change = self._update_room_with_change(
                    self._command_entity_id(command),
                    {**values, "expected_revision": command.expected_revision},
                    plan=plan,
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    _session=session,
                )
                return VenueCommandResult(value, change)
            case VenueCommandKind.DELETE_ROOM:
                value = self.delete_room(
                    self._command_entity_id(command),
                    expected_revision=self._command_revision(command),
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    reason=command.reason,
                    plan=plan,
                    _session=session,
                )
            case VenueCommandKind.CREATE_CONTACT:
                value = self.create_contact(
                    self._command_entity_id(command),
                    values,
                    plan=plan,
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    _session=session,
                )
            case VenueCommandKind.UPDATE_CONTACT:
                value = self.update_contact(
                    self._command_entity_id(command),
                    {**values, "expected_revision": command.expected_revision},
                    plan=plan,
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    _session=session,
                )
            case VenueCommandKind.DELETE_CONTACT:
                value = self.delete_contact(
                    self._command_entity_id(command),
                    expected_revision=self._command_revision(command),
                    actor_member_id=command.actor_member_id,
                    technical_actor=command.technical_actor,
                    reason=command.reason,
                    _session=session,
                )
            case VenueCommandKind.REQUEST_PROMOTION:
                value = self.request_promotion(
                    self._command_entity_id(command),
                    expected_revision=self._command_revision(command),
                    actor_member_id=self._command_actor(command),
                    reason=command.reason or "",
                    plan=plan,
                    _session=session,
                )
            case VenueCommandKind.DECIDE_PROMOTION:
                value = self.decide_promotion(
                    self._command_entity_id(command),
                    expected_revision=self._command_revision(command),
                    decision=command.decision or "",
                    reason=command.reason or "",
                    technical_actor=command.technical_actor or "",
                    plan=plan,
                    _session=session,
                )
        return VenueCommandResult(value)

    @staticmethod
    def _command_entity_id(command: VenueCommand) -> int:
        if command.entity_id is None:
            raise ValueError("Venue command needs an entity id")
        return command.entity_id

    @staticmethod
    def _command_revision(command: VenueCommand) -> int:
        if command.expected_revision is None:
            raise ValueError("Venue command needs an expected revision")
        return command.expected_revision

    @staticmethod
    def _command_actor(command: VenueCommand) -> int:
        if command.actor_member_id is None:
            raise ValueError("Venue command needs an actor")
        return command.actor_member_id

    def list_venues(self) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            venues = session.scalars(
                select(ExamVenue).order_by(ExamVenue.is_active.desc(), ExamVenue.name, ExamVenue.id)
            ).all()
            return [self._venue_payload(session, venue) for venue in venues]

    def get_venue(self, venue_id: int) -> dict[str, Any] | None:
        with session_scope(self.db_path) as session:
            venue = session.get(ExamVenue, venue_id)
            return self._venue_payload(session, venue) if venue else None

    def address_label(self, venue_id: int) -> str | None:
        """Return the address only for the authorized explicit geocoding command."""
        with session_scope(self.db_path) as session:
            venue = session.get(ExamVenue, venue_id)
            return self._address_label(vars(venue)) if venue else None

    def referenced_committee_ids(self, venue_id: int) -> frozenset[int]:
        """Return committees with a durable plan reference to this venue."""
        with session_scope(self.db_path) as session:
            rows = session.execute(
                select(ExamRound.committee_id)
                .join(ExamDay, ExamDay.exam_round_id == ExamRound.id)
                .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
                .where(ExamRoom.venue_id == venue_id)
                .distinct()
            ).scalars()
            return frozenset(rows)

    def future_impact_facts(
        self,
        venue_id: int,
        room_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> VenueFutureImpactFacts:
        """Return detached venue/room values for Planning's impact query."""
        with session_scope(self.db_path) as session:
            venue = session.get(ExamVenue, venue_id)
            room = session.get(ExamRoom, room_id) if room_id is not None else None
            if venue is None or (
                room_id is not None and (room is None or room.venue_id != venue_id)
            ):
                raise ExamVenueNotFoundError("Exam venue entity not found")
            command = dict(payload or {})
            expected = command.pop("expected_revision", None)
            entity = room if room is not None else venue
            if expected is not None:
                self._assert_revision(entity.revision, expected)
            if room is not None:
                current = {field: getattr(room, field) for field in ROOM_FIELDS}
                fields = ROOM_FIELDS
                entity_type = "room"
            else:
                current = {field: getattr(venue, field) for field in VENUE_FIELDS}
                fields = VENUE_FIELDS
                entity_type = "venue"
            before = {field: getattr(entity, field) for field in fields}
            return VenueFutureImpactFacts(
                venue_id=venue_id,
                entity_type=entity_type,
                entity_id=entity.id,
                current=current,
                before=before,
            )

    def find_duplicate_candidates(
        self,
        *,
        visible_venue_ids: frozenset[int] | None = None,
        excluded_id: int | None = None,
    ) -> tuple[dict[str, object], ...]:
        """Return only persisted candidate rows; Planning owns similarity decisions."""
        with session_scope(self.db_path) as session:
            return tuple(
                self._duplicate_candidate(venue)
                for venue in session.scalars(select(ExamVenue).order_by(ExamVenue.id))
                if venue.id != excluded_id
                and (visible_venue_ids is None or venue.id in visible_venue_ids)
            )

    def request_promotion(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        actor_member_id: int,
        reason: str,
        plan: VenueMutationPlan,
        _session: Session | None = None,
    ) -> dict[str, Any]:
        """Record one pending request without changing venue visibility."""
        with self._write_session(_session) as session:
            self._require_actor(session, actor_member_id, None)
            venue = self._venue_or_raise(session, venue_id)
            self._assert_revision(venue.revision, expected_revision)
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type="promotion_requested",
                actor_member_id=actor_member_id,
                technical_actor=None,
                reason=plan.reason,
                fields={"scope": venue.scope, "committee_id": venue.committee_id},
            )
            return self._promotion_payload(session, venue)

    def list_pending_promotions(self) -> list[dict[str, Any]]:
        with session_scope(self.db_path) as session:
            return [
                self._promotion_payload(session, venue)
                for venue in session.scalars(
                    select(ExamVenue).order_by(ExamVenue.name, ExamVenue.id)
                )
                if venue.scope == "committee"
                and self._promotion_status(session, venue.id) == "pending"
            ]

    def decide_promotion(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        decision: str,
        reason: str,
        technical_actor: str,
        plan: VenueMutationPlan,
        _session: Session | None = None,
    ) -> dict[str, Any]:
        """Approve or reject a pending promotion while preserving the venue identity."""
        with self._write_session(_session) as session:
            actor = self._require_actor(session, None, technical_actor)
            venue = self._venue_or_raise(session, venue_id)
            self._assert_revision(venue.revision, expected_revision)
            decision_reason = plan.reason
            if decision == "approve":
                venue.scope = "global"
                venue.committee_id = None
                venue.revision += 1
                session.flush()
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type=f"promotion_{'approved' if decision == 'approve' else 'rejected'}",
                actor_member_id=None,
                technical_actor=actor[1],
                reason=decision_reason,
                fields={"decision": decision},
            )
            return self._venue_payload(session, venue)

    def create_venue(
        self,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        plan: VenueMutationPlan,
        _session: Session | None = None,
    ) -> dict[str, Any]:
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            values = dict(plan.values)
            self._assert_venue_name_available(
                session,
                values["scope"],
                values["committee_id"],
                values["normalized_name"],
            )
            reason = plan.reason
            audit_values = dict(plan.audit_values or payload)
            duplicate_reason = self._optional_text(payload.get("duplicate_reason"))
            venue = ExamVenue(**values)
            session.add(venue)
            session.flush()
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type="created",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason or duplicate_reason,
                fields={
                    **values,
                    "duplicates_reviewed": audit_values.get("duplicates_reviewed") is True,
                    **(
                        {"duplicate_reason": duplicate_reason}
                        if duplicate_reason is not None
                        else {}
                    ),
                },
            )
            session.flush()
            return self._venue_payload(session, venue)

    def _update_venue_with_change(
        self,
        venue_id: int,
        payload: dict[str, Any],
        *,
        plan: VenueMutationPlan,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        _session: Session | None = None,
    ) -> tuple[dict[str, Any] | None, VenueChange | None]:
        expected_revision, command = self._expected_revision(payload)
        change: VenueChange | None = None
        changed_fields: set[str] = set()
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = session.get(ExamVenue, venue_id)
            if venue is None:
                return None, None
            self._assert_revision(venue.revision, expected_revision)
            before = {field: getattr(venue, field) for field in VENUE_FIELDS}
            values = dict(plan.values)
            self._assert_venue_name_available(
                session,
                values["scope"],
                values["committee_id"],
                values["normalized_name"],
                excluded_id=venue.id,
            )
            reason = plan.reason
            command = dict(plan.audit_values or command)
            duplicate_reason = self._optional_text(command.get("duplicate_reason"))
            was_active = bool(venue.is_active)
            changed_fields = {field for field in VENUE_FIELDS if before[field] != values[field]}
            for field, value in values.items():
                setattr(venue, field, value)
            venue.revision += 1
            session.flush()
            change = self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type=self._change_type(was_active, bool(venue.is_active)),
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason or duplicate_reason,
                fields=command,
                before=before,
                after={field: getattr(venue, field) for field in VENUE_FIELDS},
                changed_fields=changed_fields,
                meaningful_change=command.get("meaningful_change", True) is not False,
            )
            session.flush()
            result = self._venue_payload(session, venue)
        return result, change

    def delete_venue(
        self,
        venue_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
        _session: Session | None = None,
    ) -> bool:
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = session.get(ExamVenue, venue_id)
            if venue is None:
                return False
            self._assert_revision(venue.revision, expected_revision)
            if session.scalar(select(ExamRoom.id).where(ExamRoom.venue_id == venue.id).limit(1)):
                raise ExamVenueInUseError("Delete rooms before deleting a venue")
            if session.scalar(
                select(ExamVenueContact.id).where(ExamVenueContact.venue_id == venue.id).limit(1)
            ):
                raise ExamVenueInUseError("Delete contacts before deleting a venue")
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="venue",
                entity_id=venue.id,
                entity_revision=venue.revision,
                change_type="deleted",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=self._optional_text(reason),
                fields={},
            )
            session.delete(venue)
            return True

    def create_room(
        self,
        venue_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        plan: VenueMutationPlan,
        _session: Session | None = None,
    ) -> dict[str, Any]:
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = self._venue_or_raise(session, venue_id)
            values = dict(plan.values)
            reason = plan.reason
            self._assert_room_name_available(session, venue.id, values["normalized_name"])
            room = ExamRoom(venue_id=venue.id, **values)
            session.add(room)
            session.flush()
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="room",
                entity_id=room.id,
                entity_revision=room.revision,
                change_type="created",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields=values,
            )
            session.flush()
            return self._room_payload(room)

    def _update_room_with_change(
        self,
        room_id: int,
        payload: dict[str, Any],
        *,
        plan: VenueMutationPlan,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        _session: Session | None = None,
    ) -> tuple[dict[str, Any] | None, VenueChange | None]:
        expected_revision, command = self._expected_revision(payload)
        change: VenueChange | None = None
        changed_fields: set[str] = set()
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            room = session.get(ExamRoom, room_id)
            if room is None:
                return None, None
            self._assert_revision(room.revision, expected_revision)
            before = {field: getattr(room, field) for field in ROOM_FIELDS}
            values = dict(plan.values)
            reason = plan.reason
            command = dict(plan.audit_values or command)
            self._assert_room_name_available(
                session, room.venue_id, values["normalized_name"], room.id
            )
            was_active = bool(room.is_active)
            changed_fields = {field for field in ROOM_FIELDS if before[field] != values[field]}
            for field, value in values.items():
                setattr(room, field, value)
            room.revision += 1
            session.flush()
            change = self._audit(
                session,
                venue_id=room.venue_id,
                entity_type="room",
                entity_id=room.id,
                entity_revision=room.revision,
                change_type=self._change_type(was_active, bool(room.is_active)),
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields=command,
                before=before,
                after={field: getattr(room, field) for field in ROOM_FIELDS},
                changed_fields=changed_fields,
                meaningful_change=command.get("meaningful_change", True) is not False,
            )
            session.flush()
            result = self._room_payload(room)
        return result, change

    def delete_room(
        self,
        room_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
        plan: VenueMutationPlan,
        _session: Session | None = None,
    ) -> bool:
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            room = session.get(ExamRoom, room_id)
            if room is None:
                return False
            self._assert_revision(room.revision, expected_revision)
            self._assert_room_is_unused(session, room)
            self._audit(
                session,
                venue_id=room.venue_id,
                entity_type="room",
                entity_id=room.id,
                entity_revision=room.revision,
                change_type="deleted",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=self._optional_text(reason),
                fields={},
            )
            session.delete(room)
            return True

    def create_contact(
        self,
        venue_id: int,
        payload: dict[str, Any],
        *,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        plan: VenueMutationPlan,
        _session: Session | None = None,
    ) -> dict[str, Any]:
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            venue = self._venue_or_raise(session, venue_id)
            values = dict(plan.values)
            room_ids = list(plan.room_ids or ())
            reason = plan.reason
            contact = ExamVenueContact(venue_id=venue.id, **values)
            session.add(contact)
            session.flush()
            self._replace_contact_rooms(session, contact, room_ids)
            self._audit(
                session,
                venue_id=venue.id,
                entity_type="contact",
                entity_id=contact.id,
                entity_revision=contact.revision,
                change_type="created",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields={**values, "room_ids": room_ids},
            )
            session.flush()
            return self._contact_payload(session, contact)

    def update_contact(
        self,
        contact_id: int,
        payload: dict[str, Any],
        *,
        plan: VenueMutationPlan,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        _session: Session | None = None,
    ) -> dict[str, Any] | None:
        expected_revision, command = self._expected_revision(payload)
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            contact = session.get(ExamVenueContact, contact_id)
            if contact is None:
                return None
            self._assert_revision(contact.revision, expected_revision)
            values = dict(plan.values)
            room_ids = list(plan.room_ids) if plan.room_ids is not None else None
            reason = plan.reason
            was_active = bool(contact.is_active)
            for field, value in values.items():
                setattr(contact, field, value)
            if room_ids is not None:
                self._replace_contact_rooms(session, contact, room_ids)
            contact.revision += 1
            session.flush()
            self._audit(
                session,
                venue_id=contact.venue_id,
                entity_type="contact",
                entity_id=contact.id,
                entity_revision=contact.revision,
                change_type=self._change_type(was_active, bool(contact.is_active)),
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=reason,
                fields=command,
            )
            session.flush()
            return self._contact_payload(session, contact)

    def delete_contact(
        self,
        contact_id: int,
        *,
        expected_revision: int,
        actor_member_id: int | None = None,
        technical_actor: str | None = None,
        reason: str | None = None,
        _session: Session | None = None,
    ) -> bool:
        with self._write_session(_session) as session:
            actor = self._require_actor(session, actor_member_id, technical_actor)
            contact = session.get(ExamVenueContact, contact_id)
            if contact is None:
                return False
            self._assert_revision(contact.revision, expected_revision)
            self._audit(
                session,
                venue_id=contact.venue_id,
                entity_type="contact",
                entity_id=contact.id,
                entity_revision=contact.revision,
                change_type="deleted",
                actor_member_id=actor_member_id,
                technical_actor=actor[1],
                reason=self._optional_text(reason),
                fields={},
            )
            session.delete(contact)
            return True

    @staticmethod
    def _assert_room_name_available(
        session: Session, venue_id: int, normalized_name: str, excluded_id: int | None = None
    ) -> None:
        statement = select(ExamRoom.id).where(
            ExamRoom.venue_id == venue_id, ExamRoom.normalized_name == normalized_name
        )
        if excluded_id is not None:
            statement = statement.where(ExamRoom.id != excluded_id)
        if session.scalar(statement.limit(1)) is not None:
            raise ExamVenueConflictError("Room name is already used at this venue")

    @staticmethod
    def _assert_venue_name_available(
        session: Session,
        scope: str,
        committee_id: int | None,
        normalized_name: str,
        excluded_id: int | None = None,
    ) -> None:
        statement = select(ExamVenue.id).where(
            ExamVenue.scope == scope,
            ExamVenue.normalized_name == normalized_name,
        )
        if scope == "committee":
            statement = statement.where(ExamVenue.committee_id == committee_id)
        if excluded_id is not None:
            statement = statement.where(ExamVenue.id != excluded_id)
        if session.scalar(statement.limit(1)) is not None:
            raise ExamVenueConflictError("Venue name is already used within this scope")

    def _duplicate_candidates(
        self,
        session: Session,
        *,
        excluded_id: int | None,
    ) -> tuple[dict[str, object], ...]:
        return tuple(
            self._duplicate_candidate(venue)
            for venue in session.scalars(select(ExamVenue).order_by(ExamVenue.id))
            if venue.id != excluded_id
        )

    @classmethod
    def _duplicate_candidate(cls, venue: ExamVenue) -> dict[str, object]:
        source = {field: getattr(venue, field) for field in VENUE_FIELDS}
        return {
            "id": venue.id,
            **source,
            "normalized_name": venue.normalized_name,
            "address": cls._address_label(source),
        }

    def _has_future_confirmed_assignments(
        self,
        session: Session,
        venue_id: int,
        room_id: int | None = None,
    ) -> bool:
        statement = (
            select(ExamDayAssignment.id)
            .join(ExamDay, ExamDay.id == ExamDayAssignment.exam_day_id)
            .join(ExamRoom, ExamRoom.id == ExamDay.room_id)
            .where(
                ExamRoom.venue_id == venue_id,
                ExamDay.status == "confirmed",
                ExamDay.date >= date.today().isoformat(),
            )
        )
        if room_id is not None:
            statement = statement.where(ExamDay.room_id == room_id)
        return session.scalar(statement.limit(1)) is not None

    @staticmethod
    def _assert_revision(actual: int, expected: int) -> None:
        if actual != expected:
            raise ExamVenueConflictError("Venue data revision is stale")

    @staticmethod
    def _assert_room_is_unused(session: Session, room: ExamRoom) -> None:
        checks = (
            select(PlanningSettings.id).where(PlanningSettings.default_room_id == room.id),
            select(ExamDay.id).where(ExamDay.room_id == room.id),
            select(LegacyLocationRoomMapping.legacy_location_id).where(
                LegacyLocationRoomMapping.room_id == room.id
            ),
            select(ExamVenueContactRoom.contact_id).where(ExamVenueContactRoom.room_id == room.id),
        )
        if any(session.scalar(statement.limit(1)) is not None for statement in checks):
            raise ExamVenueInUseError("A used room cannot be deleted")

    def _replace_contact_rooms(
        self, session: Session, contact: ExamVenueContact, room_ids: Iterable[int]
    ) -> None:
        identifiers = list(room_ids)
        session.query(ExamVenueContactRoom).filter_by(contact_id=contact.id).delete()
        session.add_all(
            [
                ExamVenueContactRoom(contact_id=contact.id, room_id=room_id)
                for room_id in identifiers
            ]
        )

    @staticmethod
    def _room_venue_ids(session: Session, value: object) -> dict[int, int]:
        """Materialize requested room ownership facts; Planning validates the request."""
        if not isinstance(value, (list, tuple)) or any(
            not isinstance(room_id, int) or isinstance(room_id, bool) or room_id < 1
            for room_id in value
        ):
            return {}
        if not value:
            return {}
        return {
            room_id: venue_id
            for room_id, venue_id in session.execute(
                select(ExamRoom.id, ExamRoom.venue_id).where(ExamRoom.id.in_(value))
            )
        }

    @staticmethod
    def _audit(
        session: Session,
        *,
        venue_id: int,
        entity_type: str,
        entity_id: int,
        entity_revision: int,
        change_type: str,
        actor_member_id: int | None,
        technical_actor: str | None,
        reason: str | None,
        fields: dict[str, Any],
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        changed_fields: set[str] | None = None,
        meaningful_change: bool = True,
    ) -> VenueChange:
        details: dict[str, Any] = {"fields": sorted(fields), "values": fields}
        if before is not None and after is not None and changed_fields:
            details.update(
                {
                    "consequence_version": 1,
                    "before": before,
                    "after": after,
                    "changed_fields": sorted(changed_fields),
                    "meaningful_change": meaningful_change,
                }
            )
        event = ExamVenueAuditEvent(
            venue_id=venue_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_revision=entity_revision,
            change_type=change_type,
            actor_kind="member" if actor_member_id is not None else "operator",
            actor_member_id=actor_member_id,
            technical_actor=technical_actor,
            reason=reason,
            details_json=json.dumps(
                details,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        session.add(event)
        session.flush()
        return VenueChange(
            audit_id=event.id,
            venue_id=venue_id,
            entity_type=entity_type,
            entity_id=entity_id,
            revision=entity_revision,
            changed_fields=frozenset(changed_fields or ()),
        )

    def _venue_payload(self, session: Session, venue: ExamVenue) -> dict[str, Any]:
        committee = session.get(Committee, venue.committee_id) if venue.committee_id else None
        return {
            **model_to_dict(venue, EXAM_VENUE),
            "committee_name": committee.name if committee else None,
            "rooms": [
                self._room_payload(room)
                for room in session.scalars(
                    select(ExamRoom)
                    .where(ExamRoom.venue_id == venue.id)
                    .order_by(ExamRoom.is_active.desc(), ExamRoom.name, ExamRoom.id)
                )
            ],
            "contacts": [
                self._contact_payload(session, contact)
                for contact in session.scalars(
                    select(ExamVenueContact)
                    .where(ExamVenueContact.venue_id == venue.id)
                    .order_by(
                        ExamVenueContact.is_active.desc(),
                        ExamVenueContact.label,
                        ExamVenueContact.id,
                    )
                )
            ],
        }

    @staticmethod
    def _room_payload(room: ExamRoom) -> dict[str, Any]:
        return model_to_dict(room, EXAM_ROOM)

    @staticmethod
    def _contact_payload(session: Session, contact: ExamVenueContact) -> dict[str, Any]:
        return {
            **model_to_dict(contact, EXAM_VENUE_CONTACT),
            "room_ids": list(
                session.scalars(
                    select(ExamVenueContactRoom.room_id)
                    .where(ExamVenueContactRoom.contact_id == contact.id)
                    .order_by(ExamVenueContactRoom.room_id)
                )
            ),
        }

    @staticmethod
    def _change_type(was_active: bool, is_active: bool) -> str:
        if was_active != is_active:
            return "activated" if is_active else "deactivated"
        return "updated"

    @staticmethod
    def _require_actor(
        session: Session,
        actor_member_id: int | None,
        technical_actor: str | None,
    ) -> tuple[int | None, str | None]:
        if actor_member_id is not None:
            if isinstance(actor_member_id, int) and not isinstance(actor_member_id, bool):
                if session.get(CommitteeMember, actor_member_id):
                    return actor_member_id, None
            raise ExamVenueError("The audit actor does not exist")
        normalized_actor = SQLiteExamVenueRepository._optional_text(technical_actor)
        if normalized_actor:
            return None, normalized_actor
        raise ExamVenueError("A venue change needs an audit actor")

    @staticmethod
    def _promotion_status(session: Session, venue_id: int) -> str | None:
        event = session.scalars(
            select(ExamVenueAuditEvent)
            .where(
                ExamVenueAuditEvent.venue_id == venue_id,
                ExamVenueAuditEvent.change_type.in_(
                    {"promotion_requested", "promotion_approved", "promotion_rejected"}
                ),
            )
            .order_by(ExamVenueAuditEvent.id.desc())
            .limit(1)
        ).first()
        if event is None:
            return None
        return {
            "promotion_requested": "pending",
            "promotion_approved": "approved",
            "promotion_rejected": "rejected",
        }.get(event.change_type)

    def _promotion_payload(self, session: Session, venue: ExamVenue) -> dict[str, Any]:
        event = session.scalars(
            select(ExamVenueAuditEvent)
            .where(
                ExamVenueAuditEvent.venue_id == venue.id,
                ExamVenueAuditEvent.change_type == "promotion_requested",
            )
            .order_by(ExamVenueAuditEvent.id.desc())
            .limit(1)
        ).first()
        return {
            "status": self._promotion_status(session, venue.id),
            "requested_at": event.created_at if event else None,
            "requested_by_member_id": event.actor_member_id if event else None,
            "reason": event.reason if event else None,
            "venue": self._venue_payload(session, venue),
        }

    @staticmethod
    def _address_label(source: dict[str, Any]) -> str:
        return ", ".join(
            part
            for part in (
                str(source.get("street") or "").strip(),
                " ".join(
                    part
                    for part in (
                        str(source.get("postal_code") or "").strip(),
                        str(source.get("city") or "").strip(),
                    )
                    if part
                ),
                str(source.get("country") or "").strip(),
            )
            if part
        )

    @staticmethod
    def _venue_or_raise(session: Session, venue_id: int) -> ExamVenue:
        venue = session.get(ExamVenue, venue_id)
        if venue is None:
            raise ExamVenueNotFoundError("Exam venue not found")
        return venue

    @staticmethod
    def _expected_revision(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if not isinstance(payload, dict):
            raise ExamVenueError("Venue payload must be an object")
        if "expected_revision" not in payload:
            raise ExamVenueConflictError("expected_revision is required")
        expected = payload["expected_revision"]
        if not isinstance(expected, int) or isinstance(expected, bool) or expected < 1:
            raise ExamVenueConflictError("expected_revision must be a positive integer")
        return expected, {
            key: value for key, value in payload.items() if key != "expected_revision"
        }

    @staticmethod
    def _text(value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ExamVenueError("Text fields must be strings")
        return value.strip()

    @staticmethod
    def _optional_text(value: object) -> str | None:
        text = SQLiteExamVenueRepository._text(value)
        return text or None
