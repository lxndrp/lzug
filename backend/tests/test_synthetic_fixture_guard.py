from __future__ import annotations

import hashlib
import unittest

from scripts.check_synthetic_fixtures import (
    ROOT,
    run_checks,
    scan_blocked_fingerprints,
    scan_domains,
)


class SyntheticFixtureGuardTests(unittest.TestCase):
    def test_current_tree_uses_the_synthetic_fixture_policy(self) -> None:
        self.assertEqual([], run_checks())

    def test_non_reserved_demo_email_is_rejected(self) -> None:
        unsafe_email = "tester@delivery" + ".example.de"
        errors = scan_domains(ROOT / "backend/tests/synthetic-example.py", unsafe_email)

        self.assertEqual(1, len(errors))
        self.assertIn("non-reserved domain", errors[0])

    def test_blocked_fingerprint_is_rejected_without_storing_legacy_values(self) -> None:
        sentinel = "blocked synthetic sentinel"
        fingerprint_data = {
            "fingerprints": [
                {
                    "sha256": hashlib.sha256(sentinel.encode()).hexdigest(),
                    "token_count": 3,
                    "category": "sentinel",
                }
            ]
        }
        errors = scan_blocked_fingerprints(
            ROOT / "backend/tests/synthetic-example.py",
            sentinel,
            fingerprint_data,
        )

        self.assertEqual(
            ["backend/tests/synthetic-example.py: blocked legacy sentinel fingerprint detected"],
            errors,
        )


if __name__ == "__main__":
    unittest.main()
