"""Container healthcheck for the public readiness endpoint."""

from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

from .settings import RuntimeSettings


def public_health_ready(url: str | None = None) -> bool:
    """Return whether the existing public, content-free health endpoint is live."""
    try:
        target = url or RuntimeSettings.from_environment().health.url
    except ValueError:
        return False
    request = Request(target, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
            return response.status == 200 and payload.get("status") == "ok"
    except OSError, URLError, ValueError, json.JSONDecodeError:
        return False


def main() -> int:
    return 0 if public_health_ready() else 1


if __name__ == "__main__":
    sys.exit(main())
