from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from scripts.release_gate import (
    MARKER,
    REQUIRED_CHECKS,
    Candidate,
    GateError,
    authorize,
    parse_candidate,
    render_candidate,
    required_checks_pass,
)


class FakeGitHub:
    repository = "lxndrp/lzug"

    def __init__(self, *, author: str = "github-actions[bot]", permission: str = "admin"):
        candidate = Candidate("v1.2.3", "a" * 40, 308)
        self.issue = {
            "number": 400,
            "state": "closed",
            "title": "Release: v1.2.3",
            "body": render_candidate(candidate, self.repository),
            "html_url": "https://github.com/lxndrp/lzug/issues/400",
            "user": {"login": author},
            "closed_by": {"login": "maintainer"},
            "milestone": {"number": 1, "title": "v1.2.3"},
            "labels": [{"name": "type: release"}],
        }
        self.permission = permission
        self.ruleset = {
            "enforcement": "active",
            "target": "branch",
            "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"]}},
            "bypass_actors": [],
            "rules": [
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "strict_required_status_checks_policy": True,
                        "required_status_checks": [{"context": name} for name in REQUIRED_CHECKS],
                    },
                }
            ],
        }

    def repo(self, path: str = "") -> str:
        return "/repos/lxndrp/lzug" + path

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        allow_missing: bool = False,
    ) -> Any:
        del method, payload
        if path.endswith("/issues/400"):
            return self.issue
        if path.endswith("/collaborators/maintainer/permission"):
            return {"permission": self.permission}
        if path == "/repos/lxndrp/lzug":
            return {"default_branch": "master"}
        if path.endswith("/compare/" + "a" * 40 + "...master"):
            return {"status": "identical"}
        if path.endswith("/rulesets"):
            return [{"id": 1}]
        if path.endswith("/rulesets/1"):
            return self.ruleset
        if "/git/ref/tags/" in path or "/releases/tags/" in path:
            self.assert_missing_allowed(allow_missing)
            return None
        raise AssertionError(path)

    @staticmethod
    def assert_missing_allowed(allow_missing: bool) -> None:
        if not allow_missing:
            raise AssertionError("missing response was not allowed")

    def pages(self, path: str) -> list[dict[str, Any]]:
        if "/check-runs" in path:
            return [
                {
                    "name": name,
                    "head_sha": "a" * 40,
                    "conclusion": "success",
                    "completed_at": "2026-08-12T01:00:00Z",
                }
                for name in REQUIRED_CHECKS
            ]
        if "/issues?milestone=1" in path:
            return [self.issue]
        raise AssertionError(path)


class ReleaseGateContractTests(unittest.TestCase):
    def test_candidate_marker_round_trips_without_using_human_text(self) -> None:
        candidate = Candidate("v1.2.3", "a" * 40, 308)
        body = render_candidate(candidate, "lxndrp/lzug")

        self.assertEqual(candidate, parse_candidate(body))
        self.assertEqual(1, body.count(MARKER))
        self.assertIn("Quality / Overall", body)
        self.assertIn("Betrieb, Daten und Wiederherstellung", body)
        self.assertIn("GitHub-Environments `release`", body)

    def test_duplicate_or_untrusted_machine_fields_fail_closed(self) -> None:
        candidate = Candidate("v1.2.3", "a" * 40, 308)
        body = render_candidate(candidate, "lxndrp/lzug")

        for invalid in (
            body.replace(MARKER, f"{MARKER}\n{MARKER}"),
            body.replace("<!-- release-tag: v1.2.3 -->", "<!-- release-tag: latest -->"),
            body.replace(
                "<!-- candidate-sha: " + "a" * 40 + " -->",
                "<!-- candidate-sha: deadbeef -->",
            ),
            body.replace("<!-- source-issue: 308 -->", "<!-- source-issue: 0 -->"),
        ):
            with self.subTest(invalid=invalid[:80]), self.assertRaises(GateError):
                parse_candidate(invalid)

    def test_latest_result_for_every_stable_gate_must_succeed(self) -> None:
        sha = "b" * 40
        successful = [
            {
                "name": name,
                "head_sha": sha,
                "conclusion": "success",
                "completed_at": "2026-08-12T01:00:00Z",
            }
            for name in REQUIRED_CHECKS
        ]
        required_checks_pass(successful, sha)

        failed = successful + [
            {
                "name": "Quality / Security",
                "head_sha": sha,
                "conclusion": "failure",
                "completed_at": "2026-08-12T02:00:00Z",
            }
        ]
        with self.assertRaises(GateError):
            required_checks_pass(failed, sha)

        with self.assertRaises(GateError):
            required_checks_pass(successful[:-1], sha)

    def test_authorization_requires_bot_origin_and_maintainer_close(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            self.assertTrue(authorize(FakeGitHub(), 400, output))
            values = output.read_text(encoding="utf-8")
            self.assertIn("eligible=true", values)
            self.assertIn("sha=" + "a" * 40, values)

            with self.assertRaises(GateError):
                authorize(FakeGitHub(author="attacker"), 400, output)
            with self.assertRaises(GateError):
                authorize(FakeGitHub(permission="write"), 400, output)


if __name__ == "__main__":
    unittest.main()
