#!/usr/bin/env python3
"""Validate the single repository-level DEMO_URL contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.demo_deployment import DeploymentError, validate_demo_url  # noqa: E402

CANONICAL_DEMO_URL = "https://demo.lzug.repertoire.papaspyrou.name"
DEMO_VARIABLE = "DEMO_URL"
DEMO_ENVIRONMENT = "demo"


class DemoUrlContractError(RuntimeError):
    """Signal a missing, overridden, or unsafe DEMO_URL contract."""


def validate_repository_demo_url(value: str) -> str:
    """Require the confirmed public demo origin without normalizing it."""
    if value != CANONICAL_DEMO_URL:
        raise DemoUrlContractError("DEMO_URL must be the confirmed repository demo origin")
    try:
        validate_demo_url(value)
    except DeploymentError as error:
        raise DemoUrlContractError("DEMO_URL is not a valid public HTTPS origin") from error
    return value


def _variable_uri(api_url: str, repository: str, *, environment: str | None = None) -> str:
    encoded_repository = quote(repository, safe="/")
    if environment is None:
        return f"{api_url.rstrip('/')}/repos/{encoded_repository}/actions/variables/{DEMO_VARIABLE}"
    return (
        f"{api_url.rstrip('/')}/repos/{encoded_repository}/environments/"
        f"{quote(environment, safe='')}/variables/{DEMO_VARIABLE}"
    )


def _fetch_variable(
    *, api_url: str, repository: str, token: str, environment: str | None = None
) -> dict[str, Any] | None:
    request = Request(
        _variable_uri(api_url, repository, environment=environment),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except HTTPError as error:
        if environment is not None and error.code == 404:
            error.close()
            return None
        raise DemoUrlContractError(
            "Could not read the "
            f"{('Environment' if environment else 'repository')} DEMO_URL variable"
        ) from error
    except (URLError, OSError, json.JSONDecodeError) as error:
        raise DemoUrlContractError("Could not read the GitHub DEMO_URL contract") from error
    if not isinstance(payload, dict) or payload.get("name") != DEMO_VARIABLE:
        raise DemoUrlContractError("GitHub returned an invalid DEMO_URL variable document")
    return payload


def validate_github_contract(
    *, repository: str, token: str, effective_url: str, api_url: str = "https://api.github.com"
) -> None:
    """Read and validate the repository variable and absence of an Environment override."""
    validate_repository_demo_url(effective_url)
    repository_variable = _fetch_variable(api_url=api_url, repository=repository, token=token)
    if repository_variable is None:
        raise DemoUrlContractError("The repository DEMO_URL variable is missing")
    if repository_variable.get("value") != CANONICAL_DEMO_URL:
        raise DemoUrlContractError("The repository DEMO_URL variable has an unexpected value")
    environment_variable = _fetch_variable(
        api_url=api_url,
        repository=repository,
        token=token,
        environment=DEMO_ENVIRONMENT,
    )
    if environment_variable is not None:
        raise DemoUrlContractError("The demo Environment must not define a DEMO_URL override")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate one effective URL")
    validate.add_argument("--value", required=True)
    check = subparsers.add_parser("check", help="validate GitHub repository and Environment")
    check.add_argument("--repository", required=True)
    check.add_argument("--token", default=os.environ.get("GH_TOKEN", ""))
    check.add_argument("--effective-url", required=True)
    check.add_argument(
        "--api-url", default=os.environ.get("GITHUB_API_URL", "https://api.github.com")
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            validate_repository_demo_url(args.value)
        else:
            if not args.token:
                raise DemoUrlContractError("A GitHub token is required to read DEMO_URL")
            validate_github_contract(
                repository=args.repository,
                token=args.token,
                effective_url=args.effective_url,
                api_url=args.api_url,
            )
    except DemoUrlContractError as error:
        print(f"DEMO_URL contract failed: {error}", file=sys.stderr)
        return 1
    print("DEMO_URL repository contract is valid; demo Environment override is absent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
