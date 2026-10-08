"""Typed application commands for revision-bound exam lifecycle use cases."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.application.exam_lifecycle_contracts import (
    DayCloseCommand,
    DayClosureKind,
    DayReopenCommand,
    ReopeningScopeItem,
    RoundDecisionCommand,
    RoundReopenCommand,
)


def _scope_items(payload: dict[str, Any]) -> tuple[ReopeningScopeItem, ...]:
    raw = payload.get("scope", [])
    if not isinstance(raw, list):
        raise ValueError("scope muss eine Liste sein")
    items: list[ReopeningScopeItem] = []
    for value in raw:
        if not isinstance(value, Mapping) or set(value) != {"kind", "entity_id"}:
            raise ValueError("Ungültiger Korrekturumfang")
        kind, entity_id = value["kind"], value["entity_id"]
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("Ungültige Korrekturumfangsart")
        if not isinstance(entity_id, int) or isinstance(entity_id, bool):
            raise ValueError("Ungültige Kennung im Korrekturumfang")
        items.append(ReopeningScopeItem(kind, entity_id))
    return tuple(items)


def day_close_command(payload: dict[str, Any]) -> DayCloseCommand:
    return DayCloseCommand(
        revision=payload.get("revision"),
        confirmed=payload.get("confirmed") is True,
        closure_kind=DayClosureKind(payload.get("closure_type", "regular")),
        reason=payload.get("reason"),
        clarification_attempts=payload.get("clarification_attempts"),
    )


def day_reopen_command(payload: dict[str, Any]) -> DayReopenCommand:
    return DayReopenCommand(
        revision=payload.get("revision"),
        occasion=payload.get("occasion"),
        source=payload.get("source"),
        reason=payload.get("reason"),
        scope=_scope_items(payload),
    )


def round_decision_command(payload: dict[str, Any]) -> RoundDecisionCommand:
    return RoundDecisionCommand(
        revision=payload.get("revision"),
        confirmed=payload.get("confirmed") is True,
        reason=payload.get("reason"),
    )


def round_reopen_command(payload: dict[str, Any]) -> RoundReopenCommand:
    return RoundReopenCommand(
        revision=payload.get("revision"),
        occasion=payload.get("occasion"),
        source=payload.get("source"),
        reason=payload.get("reason"),
        scope=_scope_items(payload),
    )
