#!/usr/bin/env python3
"""Write the immutable identity of one generated publication artifact."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def version(command: list[str]) -> str:
    """Return the first line of a pinned build tool's version output."""

    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.splitlines()[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--demo-url", required=True)
    parser.add_argument("--source-date-epoch", required=True)
    args = parser.parse_args()
    metadata = {
        "repository_revision": args.revision,
        "base_url": args.base_url,
        "demo_url": args.demo_url,
        "source_date_epoch": int(args.source_date_epoch),
        "build_parameters": ["hugo --minify --gc", "OpenAPI export", "TypeDoc expand"],
        "tools": {
            "hugo": version(["hugo", "version"]),
            "lychee": version(["lychee", "--version"]),
            "node": version(["node", "--version"]),
            "npm": version(["npm", "--version"]),
            "task": version(["task", "--version"]),
            "typedoc": version(
                ["node", "-p", "require('./frontend/node_modules/typedoc/package.json').version"]
            ),
            "uv": version(["uv", "--version"]),
        },
    }
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "publication-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
