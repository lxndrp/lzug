"""Versioned stdin/stdout entry point for the operator CLI.

The module is intentionally usable only as ``python -m backend.admin``.  It
does not expose a socket, accept a database path on argv, or log request data.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from .admin_service import AdminOperationError, OperatorAuthService
from .database import MigrationError, database_path, database_readiness

PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
EXIT_OK = 0
EXIT_INVALID_REQUEST = 20
EXIT_NOT_READY = 21
EXIT_CONFLICT = 22
EXIT_NOT_FOUND = 23
EXIT_TOKEN_INVALID = 24
EXIT_PERSISTENCE = 25
EXIT_INTERNAL = 70

_EXIT_CODES = {
    "invalid_request": EXIT_INVALID_REQUEST,
    "database_not_ready": EXIT_NOT_READY,
    "bootstrap_not_empty": EXIT_CONFLICT,
    "account_exists": EXIT_CONFLICT,
    "account_not_found": EXIT_NOT_FOUND,
    "token_invalid": EXIT_TOKEN_INVALID,
    "persistence_error": EXIT_PERSISTENCE,
}


def _response(*, ok: bool, result: Any = None, error: dict[str, str] | None = None) -> bytes:
    payload: dict[str, Any] = {"version": PROTOCOL_VERSION, "ok": ok}
    if ok:
        payload["result"] = result
    else:
        payload["error"] = error
    return (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _write(payload: bytes) -> None:
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()


def _error(code: str, message: str) -> int:
    _write(_response(ok=False, error={"class": code, "message": message}))
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


def _execute(request: Mapping[str, Any], service: OperatorAuthService) -> dict[str, Any]:
    if request.get("version") != PROTOCOL_VERSION:
        raise AdminOperationError("invalid_request", "Unsupported protocol version")
    command = request.get("command")
    if not isinstance(command, str) or command not in {
        "bootstrap",
        "invite",
        "disable",
        "recover",
        "consume-invitation",
        "consume-recovery",
    }:
        raise AdminOperationError("invalid_request", "Unsupported admin command")
    arguments = _require_mapping(request.get("arguments", {}), "Arguments must be an object")

    if command == "bootstrap":
        issued = service.bootstrap(_require_string(arguments, "email"))
        return {
            "account": issued.account,
            "kind": issued.kind,
            "expires_at": issued.expires_at,
            "token": issued.token,
        }
    if command == "invite":
        issued = service.invite(_require_string(arguments, "email"))
        return {
            "account": issued.account,
            "kind": issued.kind,
            "expires_at": issued.expires_at,
            "token": issued.token,
        }
    if command == "disable":
        account, revoked_sessions = service.disable(_account_id(arguments))
        return {"account": account, "revoked_sessions": revoked_sessions}
    if command == "recover":
        account_value = arguments.get("account_id")
        email_value = arguments.get("email")
        account_id = None if account_value is None else _account_id(arguments)
        email = None if email_value is None else _require_string(arguments, "email")
        issued = service.recover(account_id=account_id, email=email)
        return {
            "account": issued.account,
            "kind": issued.kind,
            "expires_at": issued.expires_at,
            "token": issued.token,
        }

    token = _require_string(arguments, "token")
    kind = "invitation" if command == "consume-invitation" else "recovery"
    return {"account": service.consume(token, kind)}


def run(payload: bytes, *, service: OperatorAuthService | None = None) -> int:
    """Process exactly one protocol request and return its stable exit code."""
    if len(payload) > MAX_REQUEST_BYTES:
        return _error("invalid_request", "Request is too large")
    try:
        request = json.loads(payload.decode("utf-8"))
        request = _require_mapping(request, "Request must be an object")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error("invalid_request", "Request is not valid JSON")
    except AdminOperationError as error:
        return _error(error.code, str(error))

    try:
        active_service = service
        if active_service is None:
            readiness = database_readiness(database_path())
            if not readiness["ready"]:
                return _error("database_not_ready", "Database is not ready")
            active_service = OperatorAuthService(database_path())
        result = _execute(request, active_service)
        _write(_response(ok=True, result=result))
        return EXIT_OK
    except AdminOperationError as error:
        return _error(error.code, str(error))
    except (MigrationError, OSError, SQLAlchemyError, ValueError):
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
