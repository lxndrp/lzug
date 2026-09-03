"""Privacy-preserving structured events for stdout-based operations."""

from __future__ import annotations

import json
import os
import re
from typing import Any

DEPLOYMENT_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
SAFE_API_SEGMENTS = frozenset(
    {
        "api",
        "health",
        "ready",
        "observability",
        "frontend-errors",
        "demo",
        "status",
        "auth",
        "calendar",
        "cancellation",
        "events",
        "feed",
        "session",
        "openapi.json",
        "docs",
        "round-summary",
        "scheduling-overview",
        "planning-proposals",
        "planning-settings",
        "candidate-exam-days",
        "candidates",
        "committees",
        "confirmed-plan-days",
        "closure",
        "exam-day-assignments",
        "exam-days",
        "exam-half-years",
        "exam-rooms",
        "exam-rounds",
        "exam-venue-contacts",
        "exam-venues",
        "results",
        "ihk-status",
        "export.json",
        "export.txt",
        "exam-slots",
        "locations",
        "members",
        "memberships",
        "member-availabilities",
        "notification-channels",
        "notification-overview",
        "notification-problems",
        "notifications",
        "persons",
        "push-confirmation",
        "push-subscriptions",
        "round-candidates",
        "lifecycle",
        "reopening-impact",
        "reopenings",
        "rooms",
        "contacts",
        "terminal-status",
    }
)


def deployment_digest(environment: dict[str, str] | None = None) -> str:
    """Return only a validated immutable deployment digest or ``unknown``."""
    value = (environment or os.environ).get("LZUG_DEPLOYMENT_DIGEST", "")
    return value if DEPLOYMENT_DIGEST.fullmatch(value) else "unknown"


def safe_http_path(path: str) -> str:
    """Reduce a request path to a bounded route shape without user-provided values."""
    if path == "/":
        return "/"
    segments = [segment for segment in path.split("/") if segment]
    if not segments or segments[0] != "api":
        return "/static"
    safe = ["api"]
    for segment in segments[1:]:
        if segment.isdecimal():
            safe.append(":id")
        elif segment in SAFE_API_SEGMENTS:
            safe.append(segment)
        else:
            safe.append("unknown")
            break
    return "/" + "/".join(safe)


def emit_event(event: str, **fields: Any) -> None:
    """Emit one bounded JSON object; callers may only provide allowlisted scalars."""
    allowed_events = {
        "backend_error",
        "frontend_error",
        "http_request",
        "http_server",
        "runtime",
    }
    if event not in allowed_events:
        raise ValueError("Unsupported observability event")
    allowed_fields = {
        "bytes",
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
