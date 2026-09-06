"""Validated HTTP runtime security configuration and request rate limiting."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta

from .settings import RuntimeSettings, SecuritySettings


@dataclass(frozen=True)
class RuntimeSecurityConfig:
    """Fail-closed runtime values shared by the production HTTP handler."""

    https_only: bool
    cors_allowed_origins: frozenset[str]
    session_ttl: timedelta
    max_request_bytes: int
    auth_rate_limit: int
    auth_rate_window: timedelta

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> RuntimeSecurityConfig:
        return cls.from_settings(RuntimeSettings.from_environment(environment).security)

    @classmethod
    def from_settings(cls, settings: SecuritySettings) -> RuntimeSecurityConfig:
        return cls(
            https_only=settings.https_only,
            cors_allowed_origins=settings.cors_allowed_origins,
            session_ttl=timedelta(seconds=settings.session_ttl_seconds),
            max_request_bytes=settings.max_request_bytes,
            auth_rate_limit=settings.auth_rate_limit,
            auth_rate_window=timedelta(seconds=settings.auth_rate_window_seconds),
        )


class RequestRateLimiter:
    """Bound one process-local request class without retaining unbounded keys."""

    max_keys = 4096

    def __init__(self, limit: int, window: timedelta):
        if limit <= 0 or window <= timedelta(0):
            raise ValueError("Rate limit and window must be positive")
        self.limit = limit
        self.window_seconds = window.total_seconds()
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, now: float | None = None) -> int | None:
        """Record an allowed request or return whole seconds until retry."""
        current = time.monotonic() if now is None else now
        with self._lock:
            requests = self._requests[key]
            self._prune(requests, current)
            if len(requests) >= self.limit:
                return max(1, int(requests[0] + self.window_seconds - current + 0.999))
            requests.append(current)
            if len(self._requests) > self.max_keys:
                self._prune_keys(current, preserve=key)
            return None

    def _prune(self, requests: deque[float], now: float) -> None:
        threshold = now - self.window_seconds
        while requests and requests[0] <= threshold:
            requests.popleft()

    def _prune_keys(self, now: float, *, preserve: str) -> None:
        for key in list(self._requests):
            if key == preserve:
                continue
            requests = self._requests[key]
            self._prune(requests, now)
            if not requests:
                del self._requests[key]
        while len(self._requests) > self.max_keys:
            removable = next(key for key in self._requests if key != preserve)
            del self._requests[removable]
