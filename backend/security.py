"""Validated HTTP runtime security configuration and request rate limiting."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse


def _bounded_integer(
    environment: Mapping[str, str],
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = environment.get(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(environment: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _origins(environment: Mapping[str, str]) -> frozenset[str]:
    configured = environment.get("LZUG_CORS_ALLOWED_ORIGINS", "")
    origins = frozenset(origin.strip() for origin in configured.split(",") if origin.strip())
    for origin in origins:
        try:
            parsed = urlparse(origin)
            parsed_port = parsed.port
        except ValueError as error:
            raise ValueError(
                "LZUG_CORS_ALLOWED_ORIGINS must contain comma-separated exact HTTP origins"
            ) from error
        if (
            origin == "*"
            or any(ord(character) < 32 or ord(character) == 127 for character in origin)
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed_port is None
            and ":" in parsed.netloc.rsplit("]", 1)[-1]
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.params
            or parsed.query
            or parsed.fragment
            or origin.endswith("/")
        ):
            raise ValueError(
                "LZUG_CORS_ALLOWED_ORIGINS must contain comma-separated exact HTTP origins"
            )
    return origins


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
        values = os.environ if environment is None else environment
        return cls(
            https_only=_boolean(values, "LZUG_HTTPS_ONLY", True),
            cors_allowed_origins=_origins(values),
            session_ttl=timedelta(
                seconds=_bounded_integer(
                    values,
                    "LZUG_SESSION_TTL_SECONDS",
                    8 * 60 * 60,
                    5 * 60,
                    24 * 60 * 60,
                )
            ),
            max_request_bytes=_bounded_integer(
                values,
                "LZUG_MAX_REQUEST_BYTES",
                1024 * 1024,
                1024,
                10 * 1024 * 1024,
            ),
            auth_rate_limit=_bounded_integer(
                values,
                "LZUG_AUTH_RATE_LIMIT",
                20,
                1,
                1000,
            ),
            auth_rate_window=timedelta(
                seconds=_bounded_integer(
                    values,
                    "LZUG_AUTH_RATE_WINDOW_SECONDS",
                    60,
                    1,
                    60 * 60,
                )
            ),
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
