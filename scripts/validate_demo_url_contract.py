#!/usr/bin/env python3
"""Validate the effective DEMO_URL resolved by GitHub Actions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from demo.contract import CANONICAL_DEMO_URL as CANONICAL_DEMO_URL  # noqa: E402
from demo.contract import DemoContractError, validate_public_demo_url  # noqa: E402


class DemoUrlContractError(RuntimeError):
    """Signal a missing or unsafe effective DEMO_URL contract."""


def validate_effective_demo_url(value: str) -> str:
    """Require the confirmed public demo origin without normalizing it."""
    try:
        validate_public_demo_url(value, require_canonical=True)
    except DemoContractError as error:
        raise DemoUrlContractError(str(error)) from error
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
