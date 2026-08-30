"""Container healthcheck for the public readiness endpoint."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


def public_health_ready(url: str | None = None) -> bool:
    """Return whether the existing public, content-free health endpoint is live."""
    target = url or os.environ.get("LZUG_HEALTHCHECK_URL", "http://127.0.0.1:8000/api/health")
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
