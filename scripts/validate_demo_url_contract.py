#!/usr/bin/env python3
"""Validate the effective DEMO_URL resolved by GitHub Actions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.demo_deployment import DeploymentError, validate_demo_url  # noqa: E402

CANONICAL_DEMO_URL = "https://demo.lzug.repertoire.papaspyrou.name"


class DemoUrlContractError(RuntimeError):
    """Signal a missing or unsafe effective DEMO_URL contract."""


def validate_effective_demo_url(value: str) -> str:
    """Require the confirmed public demo origin without normalizing it."""
    if value != CANONICAL_DEMO_URL:
        raise DemoUrlContractError("DEMO_URL must be the confirmed repository demo origin")
    try:
        validate_demo_url(value)
    except DeploymentError as error:
        raise DemoUrlContractError("DEMO_URL is not a valid public HTTPS origin") from error
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate one effective URL")
    validate.add_argument("--value", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        validate_effective_demo_url(args.value)
    except DemoUrlContractError as error:
        print(f"DEMO_URL contract failed: {error}", file=sys.stderr)
        return 1
    print("The effective DEMO_URL contract is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
