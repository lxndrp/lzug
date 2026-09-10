"""Privacy-preserving structured events for stdout-based operations."""

from __future__ import annotations

import json
import re
from typing import Any

from .settings import RuntimeSettings

DEPLOYMENT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
READ_ONLY_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def deployment_digest(environment: dict[str, str] | None = None) -> str:
    """Return only a validated immutable deployment digest or ``unknown``."""
    values = (
        environment
        if environment is not None
        else RuntimeSettings.from_environment().environment_values()
    )
    value = values.get("LZUG_DEPLOYMENT_DIGEST", "")
    return value if DEPLOYMENT_DIGEST.fullmatch(value) else "unknown"


def should_emit_http_event(method: str, status: int) -> bool:
    """Keep failures and successful mutations without logging routine reads or probes."""
    return status >= 400 or method.upper() not in READ_ONLY_HTTP_METHODS


def emit_event(event: str, **fields: Any) -> None:
    """Emit one bounded JSON object; callers may only provide allowlisted scalars."""
    allowed_events = {
        "admin_socket",
        "backend_error",
        "frontend_error",
        "http_request",
        "http_server",
        "runtime",
    }
    if event not in allowed_events:
        raise ValueError("Unsupported observability event")
    allowed_fields = {
        "actor",
        "job_id",
        "correlation_id",
        "command",
        "phase",
        "category",
        "kind",
        "method",
        "path",
        "revision",
        "severity",
        "signal",
        "status",
    }
    if not set(fields) <= allowed_fields:
        raise ValueError("Unsupported observability field")
    if any(not isinstance(value, str | int | bool) for value in fields.values()):
        raise ValueError("Observability fields must be scalar")
    payload = {
        "deployment_digest": deployment_digest(),
        "event": event,
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
