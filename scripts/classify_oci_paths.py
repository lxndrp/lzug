from __future__ import annotations

import sys
from collections.abc import Iterable

NON_RUNTIME_PREFIXES = (
    ".github/ISSUE_TEMPLATE/",
    ".vscode/",
    "docs/",
    "prototypes/",
)
NON_RUNTIME_FILES = {
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    "LICENSE",
    "mkdocs.yml",
}


def is_known_non_runtime_path(path: str) -> bool:
    normalized = path.removeprefix("./")
    if normalized in NON_RUNTIME_FILES:
        return True
    if normalized.startswith(NON_RUNTIME_PREFIXES):
        return True
    return "/" not in normalized and normalized.endswith(".md")


def requires_oci_pipeline(paths: Iterable[str]) -> bool:
    changed_paths = [path for path in paths if path]
    if not changed_paths:
        return True
    return any(not is_known_non_runtime_path(path) for path in changed_paths)


def paths_from_stdin() -> list[str]:
    payload = sys.stdin.buffer.read()
    if b"\0" in payload:
        entries = payload.split(b"\0")
    else:
        entries = payload.splitlines()
    return [entry.decode("utf-8", errors="surrogateescape") for entry in entries if entry]


def main() -> int:
    relevant = requires_oci_pipeline(paths_from_stdin())
    print(f"relevant={'true' if relevant else 'false'}")
    print("classification=" + ("oci-relevant-or-unknown" if relevant else "known-non-runtime-only"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
