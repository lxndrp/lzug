"""Process-wide coordination for a feed's short lifecycle transitions and refreshes."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Event, Lock, RLock


class FeedConflictError(ValueError):
    """The observed feed generation changed before the operation could commit."""


class FeedAlreadyActiveError(ValueError):
    """The caller tried to activate an already active feed without rotation."""


class FeedRotationPendingError(ValueError):
    """Another activation or rotation is already pending."""


class FeedRevocationPendingError(ValueError):
    """A durable revocation failed and must be explicitly retried."""


class FeedSyncCancelledError(ValueError):
    """A feed refresh was fenced by a concurrent revocation."""


@dataclass
class _FeedState:
    lifecycle_lock: RLock = field(default_factory=RLock)
    sync_lock: Lock = field(default_factory=Lock)
    commit_gate: Lock = field(default_factory=Lock)
    fenced: bool = False
    cancellation: Event | None = None
    inflight_lock: Lock = field(default_factory=Lock)
    inflight: dict[object, _Flight] = field(default_factory=dict)


@dataclass
class _Flight:
    completed: Event = field(default_factory=Event)
    result: object = None
    error: BaseException | None = None


class CalendarFeedCoordinator:
    """Share feed serialization and cancellation fences across service instances."""

    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._feeds: dict[tuple[str, int], _FeedState] = {}

    def _state(self, database: str, person_id: int) -> _FeedState:
        key = (database, person_id)
        with self._registry_lock:
            return self._feeds.setdefault(key, _FeedState())

    @contextmanager
    def lifecycle(self, database: str, person_id: int) -> Iterator[_FeedState]:
        state = self._state(database, person_id)
        with state.lifecycle_lock:
            yield state

    def is_fenced(self, database: str, person_id: int) -> bool:
        return self._state(database, person_id).fenced

    def run_sync(self, database: str, person_id: int, flight_key: object, operation):
        state = self._state(database, person_id)
        with state.inflight_lock:
            flight = state.inflight.get(flight_key)
            owner = flight is None
            if owner:
                flight = _Flight()
                state.inflight[flight_key] = flight
        assert flight is not None
        if not owner:
            flight.completed.wait()
            if flight.error is not None:
                raise flight.error
            return flight.result
        try:
            with state.sync_lock:
                if state.fenced:
                    raise FeedRevocationPendingError("Calendar feed revocation is pending")
                cancellation = Event()
                state.cancellation = cancellation
                try:
                    flight.result = operation(state, cancellation)
                    return flight.result
                finally:
                    state.cancellation = None
        except BaseException as error:
            flight.error = error
            raise
        finally:
            flight.completed.set()
            with state.inflight_lock:
                if state.inflight.get(flight_key) is flight:
                    del state.inflight[flight_key]

    @contextmanager
    def serialized_commit(self, database: str, person_id: int) -> Iterator[None]:
        """Keep short lifecycle writes outside an active per-feed sync UoW."""
        state = self._state(database, person_id)
        with state.sync_lock:
            if state.fenced:
                raise FeedRevocationPendingError("Calendar feed revocation is pending")
            yield

    def fence(self, database: str, person_id: int) -> _FeedState:
        state = self._state(database, person_id)
        with state.lifecycle_lock:
            with state.commit_gate:
                state.fenced = True
                if state.cancellation is not None:
                    state.cancellation.set()
        return state

    def wait_for_sync(self, state: _FeedState) -> None:
        with state.sync_lock:
            return

    def clear_fence(self, state: _FeedState) -> None:
        with state.commit_gate:
            state.fenced = False
