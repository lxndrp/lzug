"""Container healthcheck for the public readiness endpoint."""

from __future__ import annotations

import json
import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> int:
    url = os.environ.get("LZUG_HEALTHCHECK_URL", "http://127.0.0.1:8000/api/health")
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.load(response)
            if response.status != 200 or payload.get("status") != "ok":
                return 1
    except OSError, URLError, ValueError, json.JSONDecodeError:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
