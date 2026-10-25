"""Calendar-owned use cases over consumer-defined identity, Planning, and storage ports."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, time
from threading import Event
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.calendar.feed_lifecycle import (
    CalendarFeedCoordinator,
    FeedAlreadyActiveError,
    FeedConflictError,
    FeedRevocationPendingError,
    FeedRotationPendingError,
    FeedSyncCancelledError,
)
from backend.calendar.ics import render_calendar
from backend.calendar.ports import (
    CalendarAssignmentSnapshot,
    CalendarEventProjection,
    CalendarEventSnapshot,
    CalendarFeedActivation,
    CalendarFeedSnapshot,
    CalendarFeedStatus,
    CalendarIdentitySnapshotPort,
    CalendarPlanningSnapshotPort,
    CalendarRoundSnapshot,
    CalendarScope,
    CalendarSlotSnapshot,
    CalendarUnitOfWorkFactory,
)
from backend.identity_scope import IdentityScopeCoordinator
from backend.settings import RuntimeSettings

DEFAULT_TIME_ZONE = "Europe/Berlin"


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> str:
    return (value or _now()).astimezone(UTC).isoformat(timespec="seconds")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse_local(value: str, time_zone: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value.replace(" ", "T"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=time_zone)
    return parsed.astimezone(time_zone)


class CalendarService:
    """Own feed lifecycle, event projection, and calendar-read side effects."""

    def __init__(
        self,
        unit_of_work_factory: CalendarUnitOfWorkFactory,
        planning: CalendarPlanningSnapshotPort,
        identity: CalendarIdentitySnapshotPort,
        *,
        time_zone: str | None = None,
        settings: RuntimeSettings | None = None,
        feed_coordinator: CalendarFeedCoordinator | None = None,
        identity_scope_coordinator: IdentityScopeCoordinator | None = None,
        database_id: str = "calendar",
    ) -> None:
        configured = settings or RuntimeSettings.from_environment()
        configured_zone = (
            time_zone or configured.calendar.time_zone or configured.calendar.fallback_time_zone
        )
        try:
            self.time_zone = ZoneInfo(configured_zone)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"Unknown calendar time zone: {configured_zone}") from error
        self._unit_of_work_factory = unit_of_work_factory
        self._planning = planning
        self._identity = identity
        self._feed_coordinator = feed_coordinator or CalendarFeedCoordinator()
        self._identity_scope_coordinator = identity_scope_coordinator or IdentityScopeCoordinator()
        self._database_id = database_id

    def status(self, scope: CalendarScope) -> CalendarFeedStatus:
        """Return only non-secret state for the authenticated person's feed."""
        if scope.person_id is None:
            return CalendarFeedStatus(False, None, None, self.time_zone.key)
        feed = self._feed_for_person(scope.person_id)
        return CalendarFeedStatus(
            active=bool(feed and feed.token_hash and feed.revoked_at is None),
            activated_at=(
                feed.created_at if feed and feed.token_hash and feed.revoked_at is None else None
            ),
            revoked_at=feed.revoked_at if feed else None,
            time_zone=self.time_zone.key,
        )

    def list_events(self, scope: CalendarScope) -> tuple[CalendarEventProjection, ...]:
        """Refresh before reading and return current-period events in active scope."""
        if scope.person_id is None or not scope.member_ids:
            return ()
        self.sync_person(scope.person_id)
        half_year_id = self._planning.current_half_year_id()
        if half_year_id is None:
            return ()
        active_members = self._active_member_ids(scope.person_id)
        with self._unit_of_work_factory() as work:
            events = work.events_for_members_in_period(active_members, half_year_id)
        return tuple(self._event_view(event) for event in events if event.id is not None)

    def activate(self, scope: CalendarScope, *, rotate: bool = False) -> CalendarFeedActivation:
        """Create or rotate a feed and return the token exactly once to its owner."""
        if scope.person_id is None or not scope.member_ids:
            raise ValueError("A personal membership is required")
        person_id = scope.person_id
        identity_scope = self._identity_scope(person_id)
        if not identity_scope:
            raise ValueError("A personal membership is required")
        pending_generation, revocation_generation = self._reserve_feed_activation(person_id, rotate)

        def refresh(state, cancellation):
            with self._feed_coordinator.lifecycle(self._database_id, person_id):
                latest = self._feed_for_person(person_id)
                if (
                    latest is None
                    or latest.pending_generation != pending_generation
                    or latest.revocation_generation != revocation_generation
                ):
                    raise FeedRotationPendingError("Calendar feed activation is no longer pending")
            self.sync_person(person_id, cancellation=cancellation, commit_gate=state.commit_gate)

        self._feed_coordinator.run_sync(
            self._database_id, person_id, ("pending", pending_generation), refresh
        )
        token = secrets.token_urlsafe(32)
        with self._feed_coordinator.lifecycle(self._database_id, person_id) as state:
            if state.fenced:
                raise FeedRevocationPendingError("Calendar feed revocation is pending")
            with self._feed_coordinator.serialized_commit(self._database_id, person_id):
                with self._unit_of_work_factory() as work:
                    current = work.feed_for_person(person_id)
                    if (
                        current is None
                        or current.pending_generation != pending_generation
                        or current.revocation_generation != revocation_generation
                    ):
                        raise FeedConflictError(
                            "Calendar feed generation changed before activation"
                        )
                    finalized = CalendarFeedSnapshot(
                        person_id,
                        _digest(token),
                        _timestamp(),
                        None,
                        pending_generation,
                        None,
                        revocation_generation,
                    )
                    if not work.save_feed_if_current(
                        finalized, expected_pending_generation=pending_generation
                    ):
                        raise FeedConflictError(
                            "Calendar feed generation changed before activation"
                        )
        return CalendarFeedActivation(status=self.status(scope), token=token)

    def _reserve_feed_activation(self, person_id: int, rotate: bool) -> tuple[int, int]:
        with self._feed_coordinator.lifecycle(self._database_id, person_id) as state:
            if state.fenced:
                raise FeedRevocationPendingError("Calendar feed revocation is pending")
            current = self._feed_for_person(person_id)
            if current is not None and current.pending_generation is not None:
                pending_generation = current.pending_generation
                revocation_generation = current.revocation_generation
                created_at = current.created_at
            elif current is not None and current.token_hash and current.revoked_at is None:
                if not rotate:
                    raise FeedAlreadyActiveError(
                        "Calendar feed is already active; rotate it to create a new URL"
                    )
                revocation_generation = current.revocation_generation + 1
                pending_generation = current.generation + 1
                created_at = _timestamp()
                with self._feed_coordinator.serialized_commit(self._database_id, person_id):
                    with self._unit_of_work_factory() as work:
                        if not work.save_feed_if_current(
                            CalendarFeedSnapshot(
                                person_id,
                                None,
                                created_at,
                                _timestamp(),
                                current.generation,
                                pending_generation,
                                revocation_generation,
                                _timestamp(),
                            ),
                            expected_pending_generation=current.pending_generation,
                        ):
                            raise FeedConflictError("Calendar feed changed during rotation")
            else:
                revocation_generation = current.revocation_generation if current else 0
                pending_generation = (current.generation if current else 0) + 1
                created_at = current.created_at if current else _timestamp()
                pending = CalendarFeedSnapshot(
                    person_id,
                    None,
                    created_at,
                    None,
                    current.generation if current else 0,
                    pending_generation,
                    revocation_generation,
                    current.lifecycle_revoked_at if current else None,
                )
                with self._feed_coordinator.serialized_commit(self._database_id, person_id):
                    with self._unit_of_work_factory() as work:
                        work.save_feed(pending)
        return pending_generation, revocation_generation

    def revoke(self, scope: CalendarScope) -> bool:
        if scope.person_id is None:
            return False
        person_id = scope.person_id
        state = self._feed_coordinator.fence(self._database_id, person_id)
        self._feed_coordinator.wait_for_sync(state)
        try:
            with self._feed_coordinator.lifecycle(self._database_id, person_id):
                with self._unit_of_work_factory() as work:
                    current = work.feed_for_person(person_id)
                    if current is None or (
                        current.pending_generation is None
                        and (current.token_hash is None or current.revoked_at is not None)
                    ):
                        changed = False
                    else:
                        work.save_feed(
                            CalendarFeedSnapshot(
                                person_id,
                                current.token_hash,
                                current.created_at,
                                _timestamp(),
                                current.generation,
                                None,
                                current.revocation_generation + 1,
                                _timestamp(),
                            )
                        )
                        changed = True
        except Exception as error:
            raise FeedRevocationPendingError(
                "Calendar feed revocation could not be committed"
            ) from error
        self._feed_coordinator.clear_fence(state)
        return changed

    def sync_person(
        self,
        person_id: int,
        *,
        cancellation: Event | None = None,
        commit_gate=None,
    ) -> int:
        """Refresh current-period events; this write side effect is used by reads."""
        if cancellation is None and commit_gate is None:
            identity_scope = self._identity_scope(person_id)
            return self._feed_coordinator.run_sync(
                self._database_id,
                person_id,
                ("projection", identity_scope),
                lambda state, event: self.sync_person(
                    person_id,
                    cancellation=event,
                    commit_gate=state.commit_gate,
                ),
            )
        if cancellation is None or commit_gate is None:
            raise ValueError("Feed sync cancellation and commit gate must be supplied together")
        half_year_id = self._planning.current_half_year_id()
        if half_year_id is None:
            return 0
        active_members = self._active_member_ids(person_id)
        rounds = tuple(
            snapshot
            for round_id in self._planning.confirmed_round_ids(half_year_id)
            if (snapshot := self._planning.round_snapshot(round_id, member_ids=active_members))
            is not None
            and snapshot.status == "plan_confirmed"
        )
        with self._guarded_unit_of_work(cancellation, commit_gate) as work:
            return sum(
                self._sync_round(work, item, person_id=person_id, member_ids=active_members)
                for item in rounds
            )

    def sync_round(self, round_id: int) -> int:
        """Materialize confirmed assignments within one all-or-nothing Calendar UoW."""
        snapshot = self._planning.round_snapshot(round_id)
        if snapshot is None or snapshot.status != "plan_confirmed":
            return 0
        with self._unit_of_work_factory() as work:
            return self._sync_round(work, snapshot)

    def sync_assignment(
        self, assignment_id: int, *, future_from: date | None = None
    ) -> CalendarEventSnapshot | None:
        """Refresh one assignment and return a detached event projection."""
        assignment_snapshot = self._planning.assignment_snapshot(assignment_id)
        if assignment_snapshot is None or (
            future_from is not None and assignment_snapshot.day_date < future_from.isoformat()
        ):
            return None
        round_snapshot = self._planning.round_snapshot(assignment_snapshot.round_id)
        if round_snapshot is None:
            return None
        assignment = next(
            (item for item in round_snapshot.assignments if item.id == assignment_id), None
        )
        if assignment is None:
            return None
        with self._unit_of_work_factory() as work:
            self._sync_assignments(work, round_snapshot, (assignment,))
            return self._latest_event(
                work.events_for_source(f"assignment:{assignment_id}"), assignment.member_id
            )

    def event_for_assignment(
        self, assignment_id: int, recipient_member_id: int
    ) -> CalendarEventSnapshot | None:
        """Read the latest generation for one assignment recipient."""
        with self._unit_of_work_factory() as work:
            return self._latest_event(
                work.events_for_source(f"assignment:{assignment_id}"), recipient_member_id
            )

    def cancel_assignment(self, round_id: int, assignment_id: int) -> int:
        """Cancel all event generations for one affected assignment."""
        self.sync_round(round_id)
        with self._unit_of_work_factory() as work:
            events = work.events_for_source(f"assignment:{assignment_id}")
            changed = 0
            for event in events:
                if event.status == "cancelled":
                    continue
                work.save_event(
                    replace(
                        event,
                        status="cancelled",
                        version=event.version + 1,
                        updated_at=_timestamp(),
                    )
                )
                changed += 1
            return changed

    def apply_absence_follow_up(
        self,
        assignment_id: int,
        round_id: int,
        origin_id: str,
        execution_version: int,
        action: str,
        before_image: Sequence[Mapping[str, object]],
    ) -> str:
        """Replay one immutable Execution consequence in a Calendar UoW."""
        if action not in {"update", "cancel"}:
            raise ValueError("unsupported_calendar_absence_action")
        if execution_version < 1 or not origin_id:
            raise ValueError("invalid_calendar_execution_origin")

        with self._unit_of_work_factory() as work:
            reservation = work.reserve_execution_origin(
                assignment_id, origin_id, execution_version, action
            )
            if reservation == "superseded":
                return "superseded"
            if reservation == "conflict":
                return "conflict"
            if reservation != "apply":
                raise ValueError("invalid_calendar_execution_reservation")

            prefix = f"assignment:{assignment_id}"
            events = tuple(work.events_for_source(prefix))
            snapshot = self._planning.round_snapshot(round_id)
            assignment = (
                next(
                    (item for item in snapshot.assignments if item.id == assignment_id),
                    None,
                )
                if snapshot is not None
                else None
            )

            changed = 0
            if action == "cancel":
                changed += self._cancel_replay_generations(
                    work, assignment_id, events, before_image
                )
            else:
                current_recipient = assignment.member_id if assignment is not None else None
                changed += self._cancel_replay_generations(
                    work,
                    assignment_id,
                    events,
                    before_image,
                    excluding_recipient=current_recipient,
                )
                if snapshot is not None and assignment is not None:
                    self._sync_assignment(work, snapshot, assignment)
            return "applied"

    def _cancel_replay_generations(
        self,
        work,
        assignment_id: int,
        events: tuple[CalendarEventSnapshot, ...],
        before_image: Sequence[Mapping[str, object]],
        *,
        excluding_recipient: int | None = None,
    ) -> int:
        """Cancel old generations, recreating a missing row from its frozen image."""
        by_source = {event.source_key: event for event in events}
        candidates: dict[str, CalendarEventSnapshot] = dict(by_source)
        for image in before_image:
            try:
                source_key = str(image["source_key"])
                recipient = int(image["recipient_member_id"])
                if not source_key.startswith(f"assignment:{assignment_id}:"):
                    continue
                if excluding_recipient is not None and recipient == excluding_recipient:
                    continue
                existing = by_source.get(source_key)
                if existing is None:
                    existing = self._snapshot_from_before_image(image, assignment_id)
                    if existing is not None:
                        candidates[source_key] = existing
            except KeyError, TypeError, ValueError:
                continue

        changed = 0
        for event in candidates.values():
            if event.status == "cancelled":
                continue
            if excluding_recipient is not None and event.recipient_member_id == excluding_recipient:
                continue
            work.save_event(
                replace(
                    event,
                    status="cancelled",
                    version=event.version + 1,
                    updated_at=_timestamp(),
                )
            )
            changed += 1
        return changed

    @staticmethod
    def _snapshot_from_before_image(
        image: Mapping[str, object], assignment_id: int
    ) -> CalendarEventSnapshot | None:
        try:
            return CalendarEventSnapshot(
                id=None,
                external_event_id=str(image["external_event_id"]),
                exam_half_year_id=int(image["exam_half_year_id"]),
                exam_round_id=int(image["exam_round_id"]),
                exam_day_id=(
                    int(image["exam_day_id"]) if image.get("exam_day_id") is not None else None
                ),
                exam_day_assignment_id=assignment_id,
                recipient_member_id=int(image["recipient_member_id"]),
                date=str(image["date"]),
                starts_at=str(image["starts_at"]),
                ends_at=str(image["ends_at"]),
                time_zone=str(image["time_zone"]),
                location=str(image["location"]),
                role=str(image["role"]),
                round_name=str(image["round_name"]),
                source_key=str(image["source_key"]),
                version=int(image["version"]),
                status=str(image["status"]),
                content_hash=str(image["content_hash"]),
                sent_at=(str(image["sent_at"]) if image.get("sent_at") is not None else None),
                created_at=str(image.get("created_at") or _timestamp()),
                updated_at=str(image.get("updated_at") or _timestamp()),
            )
        except KeyError, TypeError, ValueError:
            return None

    def feed_ics(self, token: str) -> str | None:
        """Return the current-period feed for a valid token and active identity scope."""
        token_hash = _digest(token)
        feed = self._active_feed(token_hash)
        if feed is None:
            return None
        person_id = feed.person_id
        initial_scope = self._identity_scope(person_id)
        if not initial_scope:
            return None

        def refresh(state, cancellation):
            self.sync_person(
                person_id,
                cancellation=cancellation,
                commit_gate=state.commit_gate,
            )

        try:
            self._feed_coordinator.run_sync(
                self._database_id, person_id, ("active", feed.generation), refresh
            )
        except FeedRevocationPendingError, FeedSyncCancelledError:
            return None
        events = self._feed_event_snapshot(token_hash, feed, initial_scope)
        if events is None:
            return None
        rendered = render_calendar(events, "Persönlicher Prüfungskalender")
        if not self._feed_read_is_current(person_id, token_hash, feed.generation, initial_scope):
            return None
        return rendered

    def _feed_event_snapshot(
        self,
        token_hash: str,
        feed: CalendarFeedSnapshot,
        initial_scope: frozenset[tuple[int, int]],
    ) -> Sequence[CalendarEventSnapshot] | None:
        person_id = feed.person_id
        half_year_id = self._planning.current_half_year_id()
        with self._feed_coordinator.lifecycle(self._database_id, person_id):
            current = self._active_feed(token_hash)
            if current is None or current.generation != feed.generation:
                return None
            if self._feed_coordinator.is_fenced(self._database_id, person_id):
                return None
            snapshot_scope = self._identity_scope(person_id)
            if snapshot_scope != initial_scope:
                return None
            if half_year_id is None:
                return ()
            current_members = frozenset(member_id for member_id, _ in snapshot_scope)
            reader = getattr(self._unit_of_work_factory, "events_for_members_in_period", None)
            if reader is not None:
                return reader(current_members, half_year_id)
            with self._unit_of_work_factory() as work:
                return work.events_for_members_in_period(current_members, half_year_id)

    def _feed_read_is_current(
        self,
        person_id: int,
        token_hash: str,
        generation: int,
        initial_scope: frozenset[tuple[int, int]],
    ) -> bool:
        if not initial_scope:
            return False
        with self._identity_scope_coordinator.guard():
            final_scope = self._identity_scope(person_id)
            if not final_scope or final_scope != initial_scope:
                return False
            with self._feed_coordinator.lifecycle(self._database_id, person_id):
                if self._feed_coordinator.is_fenced(self._database_id, person_id):
                    return False
                current = self._active_feed(token_hash)
                return current is not None and current.generation == generation

    def event_ics(self, event_id: int, scope: CalendarScope) -> str | None:
        if scope.person_id is None or not scope.member_ids:
            return None
        self.sync_person(scope.person_id)
        current_members = self._active_member_ids(scope.person_id)
        if not current_members:
            return None
        with self._unit_of_work_factory() as work:
            event = work.event_for_members(event_id, current_members)
        return render_calendar((event,), "Prüfungstermin") if event else None

    def _sync_round(
        self,
        work,
        snapshot: CalendarRoundSnapshot,
        *,
        person_id: int | None = None,
        member_ids: frozenset[int] | None = None,
        assignment_ids: frozenset[int] | None = None,
    ) -> int:
        assignments = tuple(
            item
            for item in snapshot.assignments
            if (member_ids is None or item.member_id in member_ids)
            and (assignment_ids is None or item.id in assignment_ids)
        )
        changed, touched = self._sync_assignments(work, snapshot, assignments)
        if assignment_ids is not None:
            return changed
        existing = work.events_for_round(snapshot.id, person_id=person_id)
        for event in existing:
            prefix = event.source_key.rsplit(":", 1)[0]
            if prefix not in touched and event.status != "cancelled":
                work.save_event(
                    replace(
                        event,
                        status="cancelled",
                        version=event.version + 1,
                        updated_at=_timestamp(),
                    )
                )
                changed += 1
        return changed

    def _sync_assignments(
        self,
        work,
        snapshot: CalendarRoundSnapshot,
        assignments: tuple[CalendarAssignmentSnapshot, ...],
    ) -> tuple[int, set[str]]:
        touched: set[str] = set()
        changed = 0
        for assignment in assignments:
            prefix, count = self._sync_assignment(work, snapshot, assignment)
            if prefix is not None:
                touched.add(prefix)
            changed += count
        return changed, touched

    def _sync_assignment(
        self,
        work,
        round_snapshot: CalendarRoundSnapshot,
        assignment: CalendarAssignmentSnapshot,
    ) -> tuple[str | None, int]:
        prefix = f"assignment:{assignment.id}"
        events = tuple(work.events_for_source(prefix))
        if work.execution_action(assignment.id) == "cancel":
            changed = 0
            for event in events:
                if event.status != "cancelled":
                    work.save_event(
                        replace(
                            event,
                            status="cancelled",
                            version=event.version + 1,
                            updated_at=_timestamp(),
                        )
                    )
                    changed += 1
            return prefix, changed
        section_slots = self._section_slots(assignment.slots, assignment.day_part)
        if not section_slots:
            return None, 0
        active_slots = tuple(slot for slot in section_slots if slot.status != "cancelled")
        event = self._latest_event(events, assignment.member_id)
        cancelled = assignment.day_status == "cancelled" or not active_slots
        event_slots = active_slots or section_slots
        if event and event.status == "cancelled" and not cancelled:
            event = None
        changed = 0
        for previous in events:
            if (
                previous.recipient_member_id != assignment.member_id
                and previous.status != "cancelled"
            ):
                work.save_event(
                    replace(
                        previous,
                        status="cancelled",
                        version=previous.version + 1,
                        updated_at=_timestamp(),
                    )
                )
                changed += 1
        # Source keys are durable generation identities.  Count-based allocation
        # can reuse a key after an old row has been removed or a partially
        # migrated history contains gaps, so advance from the greatest persisted
        # generation instead.
        generation = self._next_generation(prefix, events) if event is None else None
        source_key = f"{prefix}:{generation}" if generation is not None else event.source_key
        payload = self._event_payload(
            round_snapshot,
            assignment,
            event_slots,
            cancelled,
            source_key,
            event.sent_at if event else _timestamp(),
        )
        changed += self._store_event(work, event, payload, assignment.id, generation, cancelled)
        return prefix, changed

    @staticmethod
    def _next_generation(prefix: str, events: tuple[CalendarEventSnapshot, ...]) -> int:
        generations = []
        for event in events:
            origin, separator, suffix = event.source_key.rpartition(":")
            if origin != prefix or not separator:
                continue
            try:
                generations.append(int(suffix))
            except ValueError:
                continue
        return max(generations, default=0) + 1

    def _store_event(
        self,
        work,
        event: CalendarEventSnapshot | None,
        payload: dict[str, Any],
        assignment_id: int,
        generation: int | None,
        cancelled: bool,
    ) -> int:
        digest = hashlib.sha256(
            repr(sorted((key, value) for key, value in payload.items() if key != "sent_at")).encode(
                "utf-8"
            )
        ).hexdigest()
        now = _timestamp()
        if event is None:
            created = CalendarEventSnapshot(
                id=None,
                external_event_id=f"lzug-{assignment_id}-{generation}",
                exam_half_year_id=payload["exam_half_year_id"],
                exam_round_id=payload["exam_round_id"],
                exam_day_id=payload["exam_day_id"],
                exam_day_assignment_id=assignment_id,
                recipient_member_id=payload["recipient_member_id"],
                date=payload["date"],
                starts_at=payload["starts_at"],
                ends_at=payload["ends_at"],
                time_zone=payload["time_zone"],
                location=payload["location"],
                role=payload["role"],
                round_name=payload["round_name"],
                source_key=payload["source_key"],
                version=1,
                status="cancelled" if cancelled else "sent",
                content_hash=digest,
                sent_at=payload["sent_at"],
                created_at=now,
                updated_at=now,
            )
            work.save_event(created)
            return 1
        content_changed = event.content_hash != digest or (
            (event.status == "cancelled") != cancelled
        )
        status = event.status
        version = event.version
        if content_changed:
            version += 1
            status = "cancelled" if cancelled else "updated"
        updated = replace(
            event,
            external_event_id=event.external_event_id,
            exam_half_year_id=payload["exam_half_year_id"],
            exam_round_id=payload["exam_round_id"],
            exam_day_id=payload["exam_day_id"],
            exam_day_assignment_id=assignment_id,
            recipient_member_id=payload["recipient_member_id"],
            date=payload["date"],
            starts_at=payload["starts_at"],
            ends_at=payload["ends_at"],
            time_zone=payload["time_zone"],
            location=payload["location"],
            role=payload["role"],
            round_name=payload["round_name"],
            source_key=payload["source_key"],
            version=version,
            status=status,
            content_hash=digest,
            sent_at=payload["sent_at"],
            updated_at=now,
        )
        work.save_event(updated)
        return int(content_changed)

    def _event_payload(
        self,
        round_snapshot: CalendarRoundSnapshot,
        assignment: CalendarAssignmentSnapshot,
        slots: tuple[CalendarSlotSnapshot, ...],
        cancelled: bool,
        source_key: str,
        sent_at: str,
    ) -> dict[str, Any]:
        location = ", ".join(
            part
            for part in (
                assignment.venue_name,
                assignment.venue_site_name,
                assignment.room_name,
                assignment.room_building,
                assignment.room_wing,
                assignment.room_floor,
                assignment.room_number,
                assignment.venue_street,
                " ".join(
                    part for part in (assignment.venue_postal_code, assignment.venue_city) if part
                ),
                assignment.venue_country,
                assignment.venue_entrance,
                assignment.venue_travel_directions,
                assignment.room_access_notes,
            )
            if part
        )
        starts_at = min(slot.starts_at for slot in slots)
        ends_at = max(slot.ends_at for slot in slots)
        return {
            "exam_half_year_id": round_snapshot.half_year_id,
            "exam_round_id": round_snapshot.id,
            "exam_day_id": assignment.day_id,
            # These legacy hash inputs preserve idempotence for already stored events.
            # They remain private to the digest and do not cross a Calendar port.
            "exam_day_assignment_id": assignment.id,
            "secure_reference": f"/api/confirmed-plan-days/{assignment.day_id}",
            "recipient_member_id": assignment.member_id,
            "date": assignment.day_date,
            "starts_at": starts_at,
            "ends_at": ends_at,
            "time_zone": self.time_zone.key,
            "location": location,
            "role": "Fallback" if assignment.assignment_role == "fallback" else "Regulärer Prüfer",
            "round_name": round_snapshot.name,
            "source_key": source_key,
            "status": "cancelled" if cancelled else "sent",
            "sent_at": sent_at,
        }

    @staticmethod
    def _latest_event(
        events: tuple[CalendarEventSnapshot, ...] | Any, member_id: int
    ) -> CalendarEventSnapshot | None:
        matching = (event for event in events if event.recipient_member_id == member_id)
        return max(matching, key=lambda event: event.id or 0, default=None)

    def _section_slots(
        self, slots: tuple[CalendarSlotSnapshot, ...], day_part: str
    ) -> tuple[CalendarSlotSnapshot, ...]:
        if day_part == "full_day":
            return slots
        boundary = time(12, 0)
        return tuple(
            slot
            for slot in slots
            if (_parse_local(slot.starts_at, self.time_zone).time() < boundary)
            == (day_part == "morning")
        )

    @staticmethod
    def _event_view(event: CalendarEventSnapshot) -> CalendarEventProjection:
        if event.id is None:
            raise ValueError("Persisted Calendar events must have an identifier")
        return CalendarEventProjection(
            id=event.id,
            external_event_id=event.external_event_id,
            date=event.date,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            time_zone=event.time_zone,
            location=event.location,
            role=event.role,
            round_name=event.round_name,
            status=event.status,
            version=event.version,
        )

    def _active_member_ids(self, person_id: int) -> frozenset[int]:
        return frozenset(
            membership.member_id for membership in self._identity.active_memberships(person_id)
        )

    def _identity_scope(self, person_id: int) -> frozenset[tuple[int, int]]:
        return frozenset(
            (membership.member_id, membership.committee_id)
            for membership in self._identity.active_memberships(person_id)
        )

    def _feed_for_person(self, person_id: int) -> CalendarFeedSnapshot | None:
        reader = getattr(self._unit_of_work_factory, "feed_for_person", None)
        if reader is not None:
            return reader(person_id)
        with self._unit_of_work_factory() as work:
            return work.feed_for_person(person_id)

    def _active_feed(self, token_hash: str) -> CalendarFeedSnapshot | None:
        reader = getattr(self._unit_of_work_factory, "active_feed_for_token", None)
        if reader is not None:
            return reader(token_hash)
        with self._unit_of_work_factory() as work:
            return work.active_feed_for_token(token_hash)

    @contextmanager
    def _guarded_unit_of_work(self, cancellation: Event, commit_gate):
        context = self._unit_of_work_factory()
        work = context.__enter__()
        try:
            yield work
        except BaseException as error:
            context.__exit__(type(error), error, error.__traceback__)
            raise
        else:
            with commit_gate:
                if cancellation.is_set():
                    error = FeedSyncCancelledError("Calendar refresh was fenced by revocation")
                    context.__exit__(type(error), error, error.__traceback__)
                    raise error
                context.__exit__(None, None, None)

    def _calendar(self, events, name: str) -> str:
        """Compatibility helper for callers constructing a preview calendar."""
        return render_calendar(events, name)
