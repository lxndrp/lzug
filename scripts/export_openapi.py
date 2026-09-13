"""Export the application OpenAPI contract for the Hugo publication."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from backend.fastapi_assembly import FastAPIConfig, create_app


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: export_openapi.py OUTPUT")
    output = Path(sys.argv[1])
    output.parent.mkdir(parents=True, exist_ok=True)
    document = create_app(
        FastAPIConfig(db_path=Path(":memory:"), session_cookie_name="__Host-lzug_session")
    ).openapi()
    output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
