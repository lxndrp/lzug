"""Identity-owned detached lifecycle snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IdentityMemberLifecycleSnapshot:
    """Detached Identity data needed by lifecycle authorization and findings."""

    id: int
    committee_id: int
    person_id: int
    first_name: str
    last_name: str
    committee_role: str
    representing_side: str
    is_active: int


@dataclass(frozen=True)
class IdentityCommitteeLifecycleSnapshot:
    id: int
    name: str
    occupation: str
    ihk: str
