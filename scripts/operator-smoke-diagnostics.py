"""Print structural smoke evidence without dumping potentially secret responses."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def describe(directory: Path) -> None:
    stage = directory / "last-cli.stage"
    if stage.is_file():
        value = stage.read_text().strip()
        if re.fullmatch(r"[a-zA-Z0-9 /-]{1,100}", value):
            print(f"Last CLI stage={value}")
    log = directory / "backend.log"
    if log.is_file():
        # Traceback exception types identify startup failures without printing
        # exception messages, request data or log lines.
        classes = re.findall(
            r"^([A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception))(?=:|$)",
            log.read_text(errors="replace"),
            re.MULTILINE,
        )
        for name in dict.fromkeys(classes):
            print(f"Backend exception={name}")
    for name in ("last-cli.status", "last-cli.json", "last-cli.stderr"):
        path = directory / name
        if not path.is_file():
            continue
        raw = path.read_bytes()
        print(f"{name}: bytes={len(raw)}")
        if name == "last-cli.status" and re.fullmatch(rb"[0-9]+\n", raw):
            print(f"CLI exit={int(raw)}")
        if name != "last-cli.json":
            continue
        try:
            payload = json.loads(raw)
        except ValueError, UnicodeDecodeError:
            print("CLI response: invalid JSON")
            continue
        if not isinstance(payload, dict):
            print("CLI response: expected JSON object")
            continue
        for key in ("schema_version", "protocol_version", "exit_code", "ok"):
            value = payload.get(key)
            if type(value) in (int, bool):
                print(f"CLI {key}={value}")
        error = payload.get("error")
        if isinstance(error, dict):
            for key in ("class", "phase"):
                value = error.get(key)
                if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
                    print(f"CLI error.{key}={value}")


if __name__ == "__main__":
    describe(Path(sys.argv[1]))
