#!/usr/bin/env python3
"""Fail a CI gate when SARIF contains high-severity security results."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _rules(run: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rules: list[dict[str, Any]] = []
    for component_name in ("driver",):
        component = run.get("tool", {}).get(component_name, {})
        rules.extend(component.get("rules", []))
    for extension in run.get("tool", {}).get("extensions", []):
        rules.extend(extension.get("rules", []))
    return rules, {rule.get("id", ""): rule for rule in rules if rule.get("id")}


def _security_severity(result: dict[str, Any], rules: list[dict], by_id: dict[str, dict]) -> float:
    rule: dict[str, Any] = {}
    rule_index = result.get("ruleIndex")
    if isinstance(rule_index, int) and 0 <= rule_index < len(rules):
        rule = rules[rule_index]
    elif isinstance(result.get("ruleId"), str):
        rule = by_id.get(result["ruleId"], {})
    raw_value = rule.get("properties", {}).get("security-severity")
    try:
        return float(raw_value)
    except TypeError, ValueError:
        return 0.0


def findings(paths: list[Path], minimum: float) -> list[tuple[str, str, float]]:
    blocked: list[tuple[str, str, float]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for run in payload.get("runs", []):
            rules, by_id = _rules(run)
            for result in run.get("results", []):
                severity = _security_severity(result, rules, by_id)
                if severity >= minimum:
                    message = result.get("message", {}).get("text", "Security finding")
                    blocked.append((path.name, message.replace("\n", " "), severity))
    return blocked


def sarif_paths(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    if target.is_dir():
        return sorted(target.rglob("*.sarif"))
    raise ValueError(f"SARIF path does not exist: {target}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", type=Path)
    parser.add_argument("--minimum", type=float, default=7.0)
    args = parser.parse_args()
    if not 0.0 <= args.minimum <= 10.0:
        parser.error("--minimum must be between 0 and 10")
    try:
        paths = sarif_paths(args.target)
        if not paths:
            raise ValueError(f"No SARIF files found under {args.target}")
        blocked = findings(paths, args.minimum)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    if blocked:
        for filename, message, severity in blocked:
            print(f"{filename}: security-severity {severity:.1f}: {message}")
        print(f"Blocked {len(blocked)} security finding(s) at or above {args.minimum:.1f}.")
        return 1
    print(f"No security findings at or above {args.minimum:.1f} in {len(paths)} SARIF file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
