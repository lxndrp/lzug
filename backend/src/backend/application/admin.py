"""Transport-neutral application core for versioned administrator commands."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from backend.identity.admin_service import AdminOperationError, OperatorAuthService
from backend.identity.committee_admin import CommitteeAdminService
from backend.integrations.notifications import NotificationService
from backend.operations.backup_recipients import BackupRecipientRepository
from backend.operations.backup_restore import ArtifactError, ArtifactService
from backend.operations.lifecycle import LifecycleError, LifecycleService
from backend.persistence.database import (
    MigrationError,
    PersistencePaths,
)
from backend.planning.plan_consequences import PlanConsequenceService
from backend.runtime import RuntimeConflictError, RuntimeCoordinator

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
EXIT_OK = 0
EXIT_INVALID_REQUEST = 20
EXIT_NOT_READY = 21
EXIT_CONFLICT = 22
EXIT_NOT_FOUND = 23
EXIT_TOKEN_INVALID = 24
EXIT_PERSISTENCE = 25
EXIT_ARTIFACT_INVALID = 26
EXIT_RECIPIENT_KEY = 27
EXIT_INCOMPATIBLE = 28
EXIT_REPLACE_REQUIRED = 29
EXIT_INSUFFICIENT_STORAGE = 32
EXIT_ARTIFACT_OPERATION = 33
EXIT_AUTHORIZATION = 34
EXIT_INTERNAL = 70

_EXIT_CODES = {
    "invalid_request": EXIT_INVALID_REQUEST,
    "database_not_ready": EXIT_NOT_READY,
    "bootstrap_not_empty": EXIT_CONFLICT,
    "account_exists": EXIT_CONFLICT,
    "committee_conflict": EXIT_CONFLICT,
    "person_conflict": EXIT_CONFLICT,
    "account_conflict": EXIT_CONFLICT,
    "membership_conflict": EXIT_CONFLICT,
    "idempotency_conflict": EXIT_CONFLICT,
    "invitation_not_eligible": EXIT_CONFLICT,
    "account_not_found": EXIT_NOT_FOUND,
    "committee_not_found": EXIT_NOT_FOUND,
    "person_not_found": EXIT_NOT_FOUND,
    "token_invalid": EXIT_TOKEN_INVALID,
    "persistence_error": EXIT_PERSISTENCE,
    "artifact_name_invalid": EXIT_ARTIFACT_INVALID,
    "artifact_not_found": EXIT_ARTIFACT_INVALID,
    "artifact_invalid": EXIT_ARTIFACT_INVALID,
    "artifact_content_invalid": EXIT_ARTIFACT_INVALID,
    "artifact_integrity_failed": EXIT_ARTIFACT_INVALID,
    "manifest_invalid": EXIT_ARTIFACT_INVALID,
    "database_integrity_failed": EXIT_ARTIFACT_INVALID,
    "document_integrity_failed": EXIT_ARTIFACT_INVALID,
    "document_relation_failed": EXIT_ARTIFACT_INVALID,
    "authentication_key_invalid": EXIT_ARTIFACT_INVALID,
    "authentication_key_missing": EXIT_ARTIFACT_INVALID,
    "export_invalid": EXIT_ARTIFACT_INVALID,
    "export_secret_detected": EXIT_ARTIFACT_INVALID,
    "recipient_key_invalid": EXIT_RECIPIENT_KEY,
    "recipient_key_mismatch": EXIT_RECIPIENT_KEY,
    "recipient_not_configured": EXIT_RECIPIENT_KEY,
    "recipient_already_configured": EXIT_CONFLICT,
    "artifact_type_mismatch": EXIT_ARTIFACT_INVALID,
    "safety_artifact_required": EXIT_REPLACE_REQUIRED,
    "source_newer": EXIT_INCOMPATIBLE,
    "source_unsupported": EXIT_INCOMPATIBLE,
    "schema_incompatible": EXIT_INCOMPATIBLE,
    "restore_requires_backup": EXIT_INCOMPATIBLE,
    "migration_failed": EXIT_INCOMPATIBLE,
    "replace_confirmation_required": EXIT_REPLACE_REQUIRED,
    "target_changed": EXIT_REPLACE_REQUIRED,
    "target_invalid": EXIT_REPLACE_REQUIRED,
    "insufficient_storage": EXIT_INSUFFICIENT_STORAGE,
    "snapshot_failed": EXIT_ARTIFACT_OPERATION,
    "artifact_write_failed": EXIT_ARTIFACT_OPERATION,
    "restore_failed": EXIT_ARTIFACT_OPERATION,
    "postcheck_failed": EXIT_ARTIFACT_OPERATION,
    "activation_failed": EXIT_ARTIFACT_OPERATION,
    "maintenance_required": EXIT_ARTIFACT_OPERATION,
    "release_artifact_unverified": EXIT_ARTIFACT_OPERATION,
    "upgrade_backup_invalid": EXIT_ARTIFACT_INVALID,
    "irreversible_confirmation_required": EXIT_REPLACE_REQUIRED,
    "rollback_not_supported": EXIT_INCOMPATIBLE,
    "authorization_failed": EXIT_AUTHORIZATION,
}

_DIAGNOSTIC_COMMANDS = frozenset({"config", "doctor", "status"})
_ARTIFACT_COMMANDS = frozenset(
    {
        "backup-recipient-show",
        "backup-recipient-set",
        "backup-recipient-replace",
    }
)
_LIFECYCLE_COMMANDS = frozenset({"upgrade", "rollback"})
_ADMIN_COMMANDS = frozenset(
    {
        "bootstrap",
        "invite",
        "disable",
        "recover",
        "consume-invitation",
        "consume-recovery",
        "process-notifications",
        "test-notification",
        "committee-bootstrap",
        "committee-complete",
        "committee-reinvite",
        "committee-deactivate",
        "committee-reactivate",
        "plan-consequences-status",
        "retry-plan-consequences",
    }
)
_REVISION_PATTERN = re.compile(r"^(?:unknown|[0-9a-f]{40})$")
_IDENTITY_PATTERN = re.compile(
    r"^(?:development|0\.0\.0-dev\+sha\.[0-9a-f]{40}|"
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-rc\.(?:0|[1-9][0-9]*))?)$"
)


@dataclass(frozen=True)
class AdminActorContext:
    """Server-derived operator identity presented by a trusted transport adapter."""

    technical_identity: str
    is_authorized: bool


@dataclass(frozen=True)
class AdminApplicationResult:
    """Structured protocol response and its stable process-level result code."""

    response: dict[str, Any]
    exit_code: int

    def encode(self) -> bytes:
        """Encode one newline-terminated response for a byte-stream adapter."""
        return (json.dumps(self.response, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )


@dataclass(frozen=True)
class AdminServices:
    """Explicit factories for every service used by the administrator core."""

    diagnostics: Callable[[str, Mapping[str, str] | None], tuple[dict[str, Any], int]]
    readiness_probe: Callable[[Path], Mapping[str, object]]
    operator_auth_factory: Callable[[Path], OperatorAuthService]
    notification_factory: Callable[[Path], NotificationService]
    committee_factory: Callable[[Path], CommitteeAdminService]
    consequence_factory: Callable[[Path, NotificationService], PlanConsequenceService]
    artifact_factory: Callable[[PersistencePaths], ArtifactService]
    recipient_repository_factory: Callable[[ArtifactService], BackupRecipientRepository]
    lifecycle_factory: Callable[[PersistencePaths], LifecycleService]


def _response(
    *, ok: bool, result: Any = None, error: dict[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"version": PROTOCOL_VERSION, "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error
    return payload


def _error(
    code: str,
    message: str,
    *,
    phase: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> AdminApplicationResult:
    error = {"class": code, "message": message}
    if phase is not None:
        error["phase"] = phase
    if details:
        error["details"] = dict(details)
    return AdminApplicationResult(
        _response(ok=False, error=error),
        _EXIT_CODES.get(code, EXIT_INTERNAL),
    )


def _require_mapping(value: object, message: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AdminOperationError("invalid_request", message)
    return value


def _require_string(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments.get(name)
    if not isinstance(value, str) or not value.strip():
        raise AdminOperationError("invalid_request", f"Argument {name} is required")
    return value


def _account_id(arguments: Mapping[str, Any]) -> int:
    value = arguments.get("account_id")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdminOperationError("invalid_request", "Argument account_id must be positive")
    return value


def _positive_id(arguments: Mapping[str, Any], name: str) -> int:
    value = arguments.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdminOperationError("invalid_request", f"Argument {name} must be positive")
    return value


def _request_parts(request: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    if request.get("version") != PROTOCOL_VERSION:
        raise AdminOperationError("invalid_request", "Unsupported protocol version")
    command = request.get("command")
    if not isinstance(command, str) or command not in (
        _ADMIN_COMMANDS | _DIAGNOSTIC_COMMANDS | _ARTIFACT_COMMANDS | _LIFECYCLE_COMMANDS
    ):
        raise AdminOperationError("invalid_request", "Unsupported admin command")
    arguments = _require_mapping(request.get("arguments", {}), "Arguments must be an object")
    return command, arguments


def _diagnostic_client(command: str, arguments: Mapping[str, Any]) -> Mapping[str, str] | None:
    if command == "config":
        if arguments:
            raise AdminOperationError("invalid_request", "config accepts no arguments")
        return None
    if set(arguments) != {"client"}:
        raise AdminOperationError("invalid_request", f"{command} requires exact CLI build metadata")
    client = _require_mapping(arguments["client"], "CLI build metadata must be an object")
    if set(client) != {"identity", "revision"}:
        raise AdminOperationError("invalid_request", "CLI build metadata is invalid")
    identity = client.get("identity")
    revision = client.get("revision")
    if (
        not isinstance(identity, str)
        or _IDENTITY_PATTERN.fullmatch(identity) is None
        or not isinstance(revision, str)
        or _REVISION_PATTERN.fullmatch(revision) is None
    ):
        raise AdminOperationError("invalid_request", "CLI build metadata is invalid")
    return {"identity": identity, "revision": revision}


def _issued_response(issued: Any) -> dict[str, Any]:
    return {
        "account": issued.account,
        "kind": issued.kind,
        "expires_at": issued.expires_at,
        "token": issued.token,
    }


def _execute_lifecycle(
    command: str, arguments: Mapping[str, Any], lifecycle: LifecycleService
) -> dict[str, Any]:
    target = _require_mapping(arguments.get("target"), "Argument target must be release metadata")
    if command == "rollback":
        if set(arguments) != {"target"}:
            raise AdminOperationError("invalid_request", "rollback requires only target")
        return lifecycle.rollback(target)
    if set(arguments) != {"target", "backup", "confirm_irreversible"}:
        raise AdminOperationError(
            "invalid_request", "upgrade requires exact backup and target arguments"
        )
    confirmation = arguments.get("confirm_irreversible")
    if not isinstance(confirmation, bool):
        raise AdminOperationError(
            "invalid_request", "Argument confirm_irreversible must be boolean"
        )
    return lifecycle.upgrade(
        target,
        _require_mapping(arguments.get("backup"), "Argument backup must be verified evidence"),
        confirm_irreversible=confirmation,
    )


def _execute_artifact(
    command: str,
    arguments: Mapping[str, Any],
    repository: BackupRecipientRepository,
) -> dict[str, Any]:
    if command == "backup-recipient-show":
        if arguments:
            raise AdminOperationError("invalid_request", "backup-recipient-show takes no arguments")
        current = repository.show()
        if current is None:
            raise ArtifactError("recipient_not_configured", "No backup recipient is configured")
        return current
    if set(arguments) != {"recipient", "fingerprint"}:
        raise AdminOperationError("invalid_request", "Recipient update arguments are invalid")
    recipient = _require_string(arguments, "recipient")
    fingerprint = _require_string(arguments, "fingerprint")
    return (
        repository.replace(recipient, fingerprint)
        if command.endswith("replace")
        else repository.set(recipient, fingerprint)
    )


def _execute_committee(
    command: str,
    arguments: Mapping[str, Any],
    committee_service: CommitteeAdminService,
) -> dict[str, Any]:
    handler = {
        "committee-bootstrap": committee_service.bootstrap,
        "committee-complete": committee_service.complete,
        "committee-reinvite": committee_service.reinvite,
        "committee-deactivate": committee_service.deactivate,
        "committee-reactivate": committee_service.reactivate,
    }[command]
    return handler(arguments)


def _execute_notification_processing(
    notifications: NotificationService,
    consequences: PlanConsequenceService,
) -> dict[str, Any]:
    result = notifications.process_due_events()
    consequence_result = consequences.process_due()
    return {**result, "plan_consequences": consequence_result}


def _execute_plan_consequences(
    command: str,
    arguments: Mapping[str, Any],
    consequences: PlanConsequenceService,
) -> dict[str, Any]:
    revision_id = _positive_id(arguments, "revision_id")
    if command == "retry-plan-consequences":
        return consequences.retry_revision(revision_id)
    return consequences.operator_status(revision_id)


def _execute_notification_test(
    arguments: Mapping[str, Any],
    notifications: NotificationService,
) -> dict[str, Any]:
    channel = _require_string(arguments, "channel")
    if channel not in {"web_push", "email"}:
        raise AdminOperationError("invalid_request", "Argument channel must be web_push or email")
    member_id = arguments.get("member_id")
    if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
        raise AdminOperationError("invalid_request", "Argument member_id must be positive")
    return notifications.synthetic_test(member_id, channel)


def _execute_account(
    command: str, arguments: Mapping[str, Any], service: OperatorAuthService
) -> dict[str, Any]:
    if command == "bootstrap":
        return _issued_response(service.bootstrap(_require_string(arguments, "email")))
    if command == "invite":
        return _issued_response(service.invite(_require_string(arguments, "email")))
    if command == "disable":
        account, revoked_sessions = service.disable(_account_id(arguments))
        return {"account": account, "revoked_sessions": revoked_sessions}
    if command == "recover":
        account_value = arguments.get("account_id")
        email_value = arguments.get("email")
        account_id = None if account_value is None else _account_id(arguments)
        email = None if email_value is None else _require_string(arguments, "email")
        return _issued_response(service.recover(account_id=account_id, email=email))
    token = _require_string(arguments, "token")
    kind = "invitation" if command == "consume-invitation" else "recovery"
    return {"account": service.consume(token, kind)}


def _run_command(
    command: str,
    arguments: Mapping[str, Any],
    paths: PersistencePaths,
    services: AdminServices,
) -> tuple[dict[str, Any], int]:
    if command in _DIAGNOSTIC_COMMANDS:
        client = _diagnostic_client(command, arguments)
        return services.diagnostics(command, client)
    if command in _LIFECYCLE_COMMANDS:
        return _execute_lifecycle(command, arguments, services.lifecycle_factory(paths)), EXIT_OK
    if command in _ARTIFACT_COMMANDS:
        artifacts = services.artifact_factory(paths)
        repository = services.recipient_repository_factory(artifacts)
        return _execute_artifact(command, arguments, repository), EXIT_OK
    if not services.readiness_probe(paths.database)["ready"]:
        raise AdminOperationError("database_not_ready", "Database is not ready")
    if command.startswith("committee-"):
        committee = services.committee_factory(paths.database)
        return _execute_committee(command, arguments, committee), EXIT_OK
    if command in {
        "process-notifications",
        "test-notification",
        "retry-plan-consequences",
        "plan-consequences-status",
    }:
        notifications = services.notification_factory(paths.database)
        if command == "test-notification":
            return _execute_notification_test(arguments, notifications), EXIT_OK
        consequences = services.consequence_factory(paths.database, notifications)
        if command == "process-notifications":
            return _execute_notification_processing(notifications, consequences), EXIT_OK
        return _execute_plan_consequences(command, arguments, consequences), EXIT_OK
    service = services.operator_auth_factory(paths.database)
    return _execute_account(command, arguments, service), EXIT_OK


def _parse_request(payload: bytes) -> Mapping[str, Any]:
    if len(payload) > MAX_REQUEST_BYTES:
        raise AdminOperationError("invalid_request", "Request is too large")
    try:
        request = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdminOperationError("invalid_request", "Request is not valid JSON") from error
    return _require_mapping(request, "Request must be an object")


class AdminApplication:
    """Execute one administrator request without depending on a transport."""

    def __init__(
        self,
        paths: PersistencePaths,
        services: AdminServices,
        *,
        runtime: RuntimeCoordinator | None = None,
    ) -> None:
        if runtime is not None and runtime.db_path != paths.database.resolve():
            raise ValueError("Admin and runtime must share persistence")
        self.paths = paths
        self.services = services
        self.runtime = runtime

    def handle(self, payload: bytes, actor: AdminActorContext) -> AdminApplicationResult:
        """Decode and execute one bounded JSON request from any byte-stream adapter."""
        try:
            request = _parse_request(payload)
        except AdminOperationError as error:
            return _error(error.code, str(error))
        return self.execute(request, actor)

    def execute(
        self, request: Mapping[str, Any], actor: AdminActorContext
    ) -> AdminApplicationResult:
        """Execute a parsed request for a separately authenticated server actor."""
        try:
            command, arguments = _request_parts(request)
            if not actor.is_authorized or not actor.technical_identity.strip():
                raise AdminOperationError(
                    "authorization_failed", "Administrator authorization failed"
                )
            if self.runtime is not None and command in _DIAGNOSTIC_COMMANDS:
                _diagnostic_client(command, arguments)
                return AdminApplicationResult(
                    _response(ok=True, result={"runtime": self.runtime.diagnosis()}), EXIT_OK
                )
            # Lifecycle services own their exclusive admission. Ordinary admin
            # work shares the same admission as HTTP, across all its transactions.
            admission = (
                self.runtime.admit()
                if self.runtime is not None and command not in _LIFECYCLE_COMMANDS
                else nullcontext()
            )
            with admission:
                result, exit_code = _run_command(command, arguments, self.paths, self.services)
            return AdminApplicationResult(_response(ok=True, result=result), exit_code)
        except RuntimeConflictError:
            return _error("database_not_ready", "Runtime is not ready")
        except AdminOperationError as error:
            return _error(error.code, str(error))
        except ArtifactError as error:
            return _error(error.code, str(error), phase=error.phase)
        except LifecycleError as error:
            return _error(
                error.code,
                str(error),
                phase=error.phase,
                details=error.details,
            )
        except MigrationError, OSError, SQLAlchemyError, ValueError:
            return _error("persistence_error", "Admin operation failed")
        except Exception:
            return _error("internal_error", "Admin operation failed")


def invalid_protocol_result() -> AdminApplicationResult:
    """Return the stable response for an adapter-level protocol mismatch."""
    return _error("invalid_request", "Unsupported admin protocol")
