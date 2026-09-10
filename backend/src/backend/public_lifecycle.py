"""Allowlisted public projection of the authoritative runtime snapshot."""

from collections.abc import Mapping

from .runtime import RuntimeState


def public_lifecycle(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Expose only stable state codes; never forward diagnostic fields."""
    try:
        state = RuntimeState(snapshot.get("state"))
    except ValueError, TypeError:
        state = (
            RuntimeState.READY
            if snapshot.get("ready") is True
            else (
                RuntimeState.MIGRATION_REQUIRED
                if snapshot.get("reason") == "migration_required"
                else RuntimeState.ERROR
            )
        )
    if state == RuntimeState.READY and snapshot.get("ready") is not True:
        state = RuntimeState.INITIALIZING
    return {"state": state.value, "ready": state == RuntimeState.READY}


def unavailable_payload(snapshot: Mapping[str, object]) -> dict[str, object]:
    """Return the common rejection envelope without retrying a business command."""
    return {
        "error": {
            "code": "runtime_not_ready",
            "message": "Application is temporarily unavailable.",
            **public_lifecycle(snapshot),
        }
    }
