"""Detached Identity snapshots used by published calendar read projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class IdentityCalendarMember:
    """Membership and person data needed to render an assigned member."""

    member: Mapping[str, Any]
    person: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "member", MappingProxyType(dict(self.member)))
        object.__setattr__(self, "person", MappingProxyType(dict(self.person)))
