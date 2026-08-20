#!/usr/bin/env python3
"""Fail closed when Azure has generated an external Smart Detector alert rule."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import quote, urlparse


class SmartDetectionCheckError(RuntimeError):
    """The live state cannot safely be used as input to an OpenTofu plan."""


Runner = Callable[..., subprocess.CompletedProcess[str]]
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
RESOURCE_GROUP_PATTERN = re.compile(r"^[A-Za-z0-9._()\-]{1,90}$")
COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9._\-]{1,260}$")


def _run_az(arguments: Sequence[str], runner: Runner) -> str:
    result = runner(
        ["az", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SmartDetectionCheckError(
            "STOP: Azure read failed; external Smart Detection absence is unproven."
        )
    return result.stdout


def _resource_id(subscription_id: str, resource_group: str, component_name: str) -> str:
    return (
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Insights/components/{component_name}"
    ).casefold()


def verify_no_external_failure_anomalies_rule(
    subscription_id: str,
    resource_group: str,
    component_name: str,
    *,
    runner: Runner = subprocess.run,
) -> int:
    if not UUID_PATTERN.fullmatch(subscription_id):
        raise SmartDetectionCheckError("STOP: subscription ID is not a UUID.")
    if not RESOURCE_GROUP_PATTERN.fullmatch(resource_group):
        raise SmartDetectionCheckError("STOP: resource-group name is invalid.")
    if not COMPONENT_PATTERN.fullmatch(component_name):
        raise SmartDetectionCheckError("STOP: Application Insights name is invalid.")

    active_subscription = _run_az(
        ["account", "show", "--query", "id", "--output", "tsv", "--only-show-errors"],
        runner,
    ).strip()
    if active_subscription.casefold() != subscription_id.casefold():
        raise SmartDetectionCheckError("STOP: active Azure subscription does not match input.")

    collection_url = (
        "https://management.azure.com/subscriptions/"
        f"{quote(subscription_id, safe='')}/resourceGroups/"
        f"{quote(resource_group, safe='')}/providers/Microsoft.AlertsManagement/"
        "smartDetectorAlertRules?api-version=2019-06-01"
    )
    component_id = _resource_id(subscription_id, resource_group, component_name)
    expected_name = f"Failure Anomalies - {component_name}".casefold()
    matching_rules = 0
    inspected_rules = 0
    next_url: str | None = collection_url
    visited_urls: set[str] = set()
    while next_url is not None:
        parsed_url = urlparse(next_url)
        if parsed_url.scheme != "https" or parsed_url.hostname != "management.azure.com":
            raise SmartDetectionCheckError(
                "STOP: Azure Smart Detection pagination target is not trusted."
            )
        if next_url in visited_urls or len(visited_urls) >= 100:
            raise SmartDetectionCheckError(
                "STOP: Azure Smart Detection pagination cannot be completed safely."
            )
        visited_urls.add(next_url)

        raw = _run_az(
            [
                "rest",
                "--method",
                "get",
                "--url",
                next_url,
                "--output",
                "json",
                "--only-show-errors",
            ],
            runner,
        )
        try:
            payload: Any = json.loads(raw)
        except json.JSONDecodeError as error:
            raise SmartDetectionCheckError(
                "STOP: Azure Smart Detection response is not valid JSON."
            ) from error

        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise SmartDetectionCheckError(
                "STOP: Azure Smart Detection response has an unexpected schema."
            )

        for rule in payload["value"]:
            if not isinstance(rule, dict) or not isinstance(rule.get("properties"), dict):
                raise SmartDetectionCheckError(
                    "STOP: Azure Smart Detection rule has an unexpected schema."
                )
            name = rule.get("name")
            scope = rule["properties"].get("scope", [])
            if (
                not isinstance(name, str)
                or not isinstance(scope, list)
                or not all(isinstance(value, str) for value in scope)
            ):
                raise SmartDetectionCheckError(
                    "STOP: Azure Smart Detection rule has an unexpected schema."
                )
            if name.casefold() == expected_name or component_id in {
                value.rstrip("/").casefold() for value in scope
            }:
                matching_rules += 1
            inspected_rules += 1

        following_url = payload.get("nextLink")
        if following_url is not None and not isinstance(following_url, str):
            raise SmartDetectionCheckError(
                "STOP: Azure Smart Detection pagination has an unexpected schema."
            )
        next_url = following_url or None

    if matching_rules:
        raise SmartDetectionCheckError(
            "STOP: an external Failure Anomalies Smart Detector rule targets the demo component; "
            "review live drift before planning."
        )
    return inspected_rules


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only pre-plan check for Azure-generated Failure Anomalies drift."
    )
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--component-name", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        count = verify_no_external_failure_anomalies_rule(
            arguments.subscription_id,
            arguments.resource_group,
            arguments.component_name,
        )
    except SmartDetectionCheckError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        "OK: no external Smart Detector alert rule targets the demo Application Insights "
        f"component ({count} resource-group rules inspected)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
