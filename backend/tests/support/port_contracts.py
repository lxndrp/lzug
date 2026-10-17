"""Runtime assertions for values crossing application-owned ports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass

from sqlalchemy import inspect
from sqlalchemy.orm import Query, Session
from sqlalchemy.sql.elements import ClauseElement


def assert_materialized_port_value(test_case, value: object) -> None:
    """Reject live SQLAlchemy objects anywhere in a materialized port result."""
    pending = [value]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if current is None or isinstance(current, (str, bytes, int, float, bool)):
            continue
        identity = id(current)
        if identity in visited:
            continue
        visited.add(identity)

        test_case.assertFalse(
            isinstance(current, (Session, Query, ClauseElement))
            or (isinstance(current, type) and issubclass(current, (Session, Query, ClauseElement))),
            f"SQLAlchemy query/session value crossed a port: {type(current).__name__}",
        )
        test_case.assertIsNone(
            inspect(current, raiseerr=False),
            f"SQLAlchemy mapped value crossed a port: {type(current).__name__}",
        )

        if isinstance(current, Mapping):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, (list, tuple, set, frozenset)):
            pending.extend(current)
        elif is_dataclass(current) and not isinstance(current, type):
            pending.extend(getattr(current, field.name) for field in fields(current))
