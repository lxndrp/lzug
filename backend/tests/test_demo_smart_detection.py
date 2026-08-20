from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock

from scripts.check_demo_smart_detection import (
    SmartDetectionCheckError,
    verify_no_external_failure_anomalies_rule,
)


class DemoSmartDetectionCheckTests(unittest.TestCase):
    subscription_id = "00000000-0000-0000-0000-000000000000"
    resource_group = "rg-lzug-demo"
    component_name = "lzug-demo-uptime"
    component_id = (
        "/subscriptions/00000000-0000-0000-0000-000000000000/"
        "resourceGroups/rg-lzug-demo/providers/Microsoft.Insights/components/lzug-demo-uptime"
    )

    def test_repository_binds_create_time_opt_out_and_quality_check(self) -> None:
        providers = Path("infra/demo/providers.tf").read_text(encoding="utf-8")
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")

        self.assertIn(
            "disable_generated_rule = local.application_insights_generated_rule_disabled",
            providers,
        )
        self.assertIn("backend.tests.test_demo_smart_detection", taskfile)

    def runner_for(self, payload: object, *, active_subscription: str | None = None) -> Mock:
        return Mock(
            side_effect=[
                subprocess.CompletedProcess(
                    [],
                    0,
                    (active_subscription or self.subscription_id) + "\n",
                    "",
                ),
                subprocess.CompletedProcess([], 0, json.dumps(payload), ""),
            ]
        )

    def runner_for_pages(self, *payloads: object) -> Mock:
        return Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, self.subscription_id + "\n", ""),
                *[
                    subprocess.CompletedProcess([], 0, json.dumps(payload), "")
                    for payload in payloads
                ],
            ]
        )

    def verify(self, runner: Mock) -> int:
        return verify_no_external_failure_anomalies_rule(
            self.subscription_id,
            self.resource_group,
            self.component_name,
            runner=runner,
        )

    def test_absent_external_rule_is_safe_for_later_plan_gate(self) -> None:
        runner = self.runner_for({"value": []})

        self.assertEqual(0, self.verify(runner))
        self.assertEqual(2, runner.call_count)
        rest_command = runner.call_args_list[1].args[0]
        self.assertEqual(["az", "rest", "--method", "get"], rest_command[:4])
        self.assertTrue(
            any(
                "smartDetectorAlertRules?api-version=2019-06-01" in argument
                for argument in rest_command
            )
        )

    def test_failure_anomalies_name_stops_even_without_scope(self) -> None:
        runner = self.runner_for(
            {
                "value": [
                    {
                        "name": "Failure Anomalies - lzug-demo-uptime",
                        "properties": {"scope": []},
                    }
                ]
            }
        )

        with self.assertRaisesRegex(SmartDetectionCheckError, "STOP: an external"):
            self.verify(runner)

    def test_any_external_rule_scoped_to_component_stops(self) -> None:
        runner = self.runner_for(
            {
                "value": [
                    {
                        "name": "Unexpected detector",
                        "properties": {"scope": [self.component_id.upper() + "/"]},
                    }
                ]
            }
        )

        with self.assertRaisesRegex(SmartDetectionCheckError, "review live drift"):
            self.verify(runner)

    def test_unrelated_rule_does_not_block(self) -> None:
        runner = self.runner_for(
            {
                "value": [
                    {
                        "name": "Failure Anomalies - another-component",
                        "properties": {
                            "scope": [
                                self.component_id.replace(self.component_name, "another-component")
                            ]
                        },
                    }
                ]
            }
        )

        self.assertEqual(1, self.verify(runner))

    def test_paginated_rule_scope_still_stops(self) -> None:
        runner = self.runner_for_pages(
            {
                "value": [],
                "nextLink": (
                    "https://management.azure.com/subscriptions/00000000-0000-0000-"
                    "0000-000000000000/providers/Microsoft.AlertsManagement/"
                    "smartDetectorAlertRules?api-version=2019-06-01&$skiptoken=next"
                ),
            },
            {
                "value": [
                    {
                        "name": "Unexpected detector",
                        "properties": {"scope": [self.component_id]},
                    }
                ]
            },
        )

        with self.assertRaisesRegex(SmartDetectionCheckError, "review live drift"):
            self.verify(runner)
        self.assertEqual(3, runner.call_count)

    def test_untrusted_pagination_target_fails_closed(self) -> None:
        runner = self.runner_for({"value": [], "nextLink": "https://example.invalid/next"})

        with self.assertRaisesRegex(SmartDetectionCheckError, "not trusted"):
            self.verify(runner)
        self.assertEqual(2, runner.call_count)

    def test_subscription_mismatch_stops_before_live_rule_read(self) -> None:
        runner = self.runner_for(
            {"value": []},
            active_subscription="11111111-1111-1111-1111-111111111111",
        )

        with self.assertRaisesRegex(SmartDetectionCheckError, "subscription does not match"):
            self.verify(runner)
        self.assertEqual(1, runner.call_count)

    def test_malformed_response_fails_closed_without_echoing_payload(self) -> None:
        marker = "sensitive-marker"
        runner = self.runner_for({"value": [{"properties": {"scope": marker}}]})

        with self.assertRaises(SmartDetectionCheckError) as context:
            self.verify(runner)
        self.assertNotIn(marker, str(context.exception))


if __name__ == "__main__":
    unittest.main()
