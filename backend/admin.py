"""Versioned stdin/stdout entry point for the operator CLI.

The module is intentionally usable only as ``python -m backend.admin``.  It
does not expose a socket, accept a database path on argv, or log request data.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from .admin_service import AdminOperationError, OperatorAuthService
from .backup_recipients import BackupRecipientRepository
from .backup_restore import ArtifactError, ArtifactService
from .committee_admin import CommitteeAdminService
from .database import MigrationError, database_path, database_readiness, persistence_paths
from .diagnostics import run_diagnostics
from .lifecycle import LifecycleError, LifecycleService
from .notifications import NotificationService
from .plan_consequences import PlanConsequenceService

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


def _response(*, ok: bool, result: Any = None, error: dict[str, Any] | None = None) -> bytes:
    payload: dict[str, Any] = {"version": PROTOCOL_VERSION, "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _write(payload: bytes) -> None:
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _error(
    code: str,
    message: str,
    *,
    phase: str | None = None,
    details: Mapping[str, Any] | None = None,
) -> int:
    error = {"class": code, "message": message}
    if phase is not None:
        error["phase"] = phase
    if details:
        error["details"] = dict(details)
    _write(_response(ok=False, error=error))
    return _EXIT_CODES.get(code, EXIT_INTERNAL)


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
    command: str, arguments: Mapping[str, Any], lifecycle: LifecycleService | None
) -> dict[str, Any]:
    active_lifecycle = lifecycle or LifecycleService()
    target = _require_mapping(arguments.get("target"), "Argument target must be release metadata")
    if command == "rollback":
        if set(arguments) != {"target"}:
            raise AdminOperationError("invalid_request", "rollback requires only target")
        return active_lifecycle.rollback(target)
    if set(arguments) != {"target", "backup", "confirm_irreversible"}:
        raise AdminOperationError(
            "invalid_request", "upgrade requires exact backup and target arguments"
        )
    confirmation = arguments.get("confirm_irreversible")
    if not isinstance(confirmation, bool):
        raise AdminOperationError(
            "invalid_request", "Argument confirm_irreversible must be boolean"
        )
    return active_lifecycle.upgrade(
        target,
        _require_mapping(arguments.get("backup"), "Argument backup must be verified evidence"),
        confirm_irreversible=confirmation,
    )


def _execute_artifact(
    command: str, arguments: Mapping[str, Any], artifacts: ArtifactService | None
) -> dict[str, Any]:
    active_artifacts = artifacts or ArtifactService()
    repository = BackupRecipientRepository(
        active_artifacts.paths.database,
        environment=active_artifacts.environment,
    )
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
    service: OperatorAuthService,
    committee_service: CommitteeAdminService | None,
) -> dict[str, Any]:
    active_committee_service = committee_service or CommitteeAdminService(service.db_path)
    handler = {
        "committee-bootstrap": active_committee_service.bootstrap,
        "committee-complete": active_committee_service.complete,
        "committee-reinvite": active_committee_service.reinvite,
        "committee-deactivate": active_committee_service.deactivate,
        "committee-reactivate": active_committee_service.reactivate,
    }[command]
    return handler(arguments)


def _execute_notification_processing(
    service: OperatorAuthService,
    notifications: NotificationService | None,
    consequences: PlanConsequenceService | None,
) -> dict[str, Any]:
    active_notifications = notifications or NotificationService(service.db_path)
    result = active_notifications.process_due_events()
    consequence_result = (
        consequences or PlanConsequenceService(service.db_path, active_notifications)
    ).process_due()
    return {**result, "plan_consequences": consequence_result}


def _execute_plan_consequences(
    command: str,
    arguments: Mapping[str, Any],
    service: OperatorAuthService,
    consequences: PlanConsequenceService | None,
) -> dict[str, Any]:
    revision_id = _positive_id(arguments, "revision_id")
    active_consequences = consequences or PlanConsequenceService(service.db_path)
    if command == "retry-plan-consequences":
        return active_consequences.retry_revision(revision_id)
    return active_consequences.operator_status(revision_id)


def _execute_notification_test(
    arguments: Mapping[str, Any],
    service: OperatorAuthService,
    notifications: NotificationService | None,
) -> dict[str, Any]:
    channel = _require_string(arguments, "channel")
    if channel not in {"web_push", "email"}:
        raise AdminOperationError("invalid_request", "Argument channel must be web_push or email")
    member_id = arguments.get("member_id")
    if isinstance(member_id, bool) or not isinstance(member_id, int) or member_id <= 0:
        raise AdminOperationError("invalid_request", "Argument member_id must be positive")
    return (notifications or NotificationService(service.db_path)).synthetic_test(
        member_id, channel
    )


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


def _execute(
    command: str,
    arguments: Mapping[str, Any],
    service: OperatorAuthService | None,
    notifications: NotificationService | None = None,
    committee_service: CommitteeAdminService | None = None,
    consequences: PlanConsequenceService | None = None,
    artifacts: ArtifactService | None = None,
    lifecycle: LifecycleService | None = None,
) -> dict[str, Any]:
    if command in _LIFECYCLE_COMMANDS:
        return _execute_lifecycle(command, arguments, lifecycle)
    if command in _ARTIFACT_COMMANDS:
        return _execute_artifact(command, arguments, artifacts)
    if service is None:
        raise AdminOperationError("database_not_ready", "Database is not ready")
    if command.startswith("committee-"):
        return _execute_committee(command, arguments, service, committee_service)
    if command == "process-notifications":
        return _execute_notification_processing(service, notifications, consequences)
    if command in {"retry-plan-consequences", "plan-consequences-status"}:
        return _execute_plan_consequences(command, arguments, service, consequences)
    if command == "test-notification":
        return _execute_notification_test(arguments, service, notifications)
    return _execute_account(command, arguments, service)


@dataclass
class _CommandDependencies:
    service: OperatorAuthService | None
    notifications: NotificationService | None
    committee_service: CommitteeAdminService | None
    consequences: PlanConsequenceService | None
    artifacts: ArtifactService | None
    lifecycle: LifecycleService | None


def _prepare_dependencies(
    command: str,
    service: OperatorAuthService | None,
    notifications: NotificationService | None,
    committee_service: CommitteeAdminService | None,
    consequences: PlanConsequenceService | None,
    artifacts: ArtifactService | None,
    lifecycle: LifecycleService | None,
) -> _CommandDependencies:
    active_artifacts = artifacts
    if command in _ARTIFACT_COMMANDS and active_artifacts is None:
        active_artifacts = ArtifactService(persistence_paths())
    active_lifecycle = lifecycle
    if command in _LIFECYCLE_COMMANDS and active_lifecycle is None:
        active_lifecycle = LifecycleService(persistence_paths())
    active_service = service
    if active_service is None and command not in (_ARTIFACT_COMMANDS | _LIFECYCLE_COMMANDS):
        readiness = database_readiness(database_path())
        if not readiness["ready"]:
            raise AdminOperationError("database_not_ready", "Database is not ready")
        active_service = OperatorAuthService(database_path())
    return _CommandDependencies(
        active_service,
        notifications,
        committee_service,
        consequences,
        active_artifacts,
        active_lifecycle,
    )


def _run_command(
    command: str,
    arguments: Mapping[str, Any],
    service: OperatorAuthService | None,
    notifications: NotificationService | None,
    committee_service: CommitteeAdminService | None,
    consequences: PlanConsequenceService | None,
    artifacts: ArtifactService | None,
    lifecycle: LifecycleService | None,
) -> tuple[dict[str, Any], int]:
    if command in _DIAGNOSTIC_COMMANDS:
        client = _diagnostic_client(command, arguments)
        return run_diagnostics(command, client)
    dependencies = _prepare_dependencies(
        command,
        service,
        notifications,
        committee_service,
        consequences,
        artifacts,
        lifecycle,
    )
    return (
        _execute(
            command,
            arguments,
            dependencies.service,
            dependencies.notifications,
            dependencies.committee_service,
            dependencies.consequences,
            dependencies.artifacts,
            dependencies.lifecycle,
        ),
        EXIT_OK,
    )


def _parse_request(payload: bytes) -> tuple[str, Mapping[str, Any]]:
    if len(payload) > MAX_REQUEST_BYTES:
        raise AdminOperationError("invalid_request", "Request is too large")
    try:
        request = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdminOperationError("invalid_request", "Request is not valid JSON") from error
    return _request_parts(_require_mapping(request, "Request must be an object"))


def run(
    payload: bytes,
    *,
    service: OperatorAuthService | None = None,
    notifications: NotificationService | None = None,
    committee_service: CommitteeAdminService | None = None,
    consequences: PlanConsequenceService | None = None,
    artifacts: ArtifactService | None = None,
    lifecycle: LifecycleService | None = None,
) -> int:
    """Process exactly one protocol request and return its stable exit code."""
    try:
        command, arguments = _parse_request(payload)
    except AdminOperationError as error:
        return _error(error.code, str(error))

    try:
        result, exit_code = _run_command(
            command,
            arguments,
            service,
            notifications,
            committee_service,
            consequences,
            artifacts,
            lifecycle,
        )
        _write(_response(ok=True, result=result))
        return exit_code
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


def main() -> int:
    """Read one request from stdin without reflecting it to output or logs."""
    if sys.argv[1:] != ["--protocol", str(PROTOCOL_VERSION)]:
        return _error("invalid_request", "Unsupported admin protocol")
    payload = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    return run(payload)


if __name__ == "__main__":
    raise SystemExit(main())
