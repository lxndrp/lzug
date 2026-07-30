from __future__ import annotations

import hashlib
import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_ci_artifacts import scan_file
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

    def test_binary_screenshot_is_not_decoded_as_text(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            screenshot = Path(temporary_directory) / "screenshot.jpeg"
            screenshot.write_bytes(b"tester@delivery" + b".example.de\x00binary")

            self.assertEqual([], scan_file(screenshot))

    def test_text_hits_are_detected_inside_and_outside_archives(self) -> None:
        unsafe_email = "tester@delivery" + ".example.de"
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            text_file = root / "report.json"
            text_file.write_text(f'{{"email": "{unsafe_email}"}}', encoding="utf-8")

            archive = root / "playwright-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("screenshot.jpeg", unsafe_email.encode("utf-8"))
                outer.writestr("trace.trace", f'{{"email": "{unsafe_email}"}}')

            direct_errors = scan_file(text_file)
            archive_errors = scan_file(archive)

            self.assertEqual(1, len(direct_errors))
            self.assertIn("non-reserved domain", direct_errors[0])
            self.assertEqual(1, len(archive_errors))
            self.assertIn("non-reserved domain", archive_errors[0])

    def test_nested_archive_text_is_scanned_without_scanning_binary_members(self) -> None:
        unsafe_email = "tester@delivery" + ".example.de"
        with TemporaryDirectory() as temporary_directory:
            nested_buffer = io.BytesIO()
            with zipfile.ZipFile(nested_buffer, "w") as nested:
                nested.writestr("trace.trace", unsafe_email)
                nested.writestr("screenshot.png", unsafe_email.encode("utf-8"))

            archive = Path(temporary_directory) / "nested-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("data/resources.zip", nested_buffer.getvalue())

            errors = scan_file(archive)

            self.assertEqual(1, len(errors))
            self.assertIn("non-reserved domain", errors[0])

    def test_sensitive_text_is_still_detected_inside_archive(self) -> None:
        sensitive_header = "Authorization: Bearer " + "redacted-token"
        with TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "trace-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("trace.network", sensitive_header)

            errors = scan_file(archive)

            self.assertEqual(1, len(errors))
            self.assertIn("sensitive CI artifact content detected", errors[0])


if __name__ == "__main__":
    unittest.main()
