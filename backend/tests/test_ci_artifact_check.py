from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_ci_artifacts import scan_file


class CiArtifactCheckTests(unittest.TestCase):
    def test_binary_screenshot_is_not_decoded_as_text(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            screenshot = Path(temporary_directory) / "screenshot.jpeg"
            screenshot.write_bytes(b"binary\x00content")

            self.assertEqual([], scan_file(screenshot))

    def test_text_is_not_rejected_for_test_data_content(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            report = Path(temporary_directory) / "report.json"
            report.write_text('{"email": "tester@delivery.example.de"}', encoding="utf-8")

            self.assertEqual([], scan_file(report))

    def test_nested_archive_text_is_scanned_without_scanning_binary_members(self) -> None:
        sensitive_header = "Authorization: Bearer redacted-token"
        with TemporaryDirectory() as temporary_directory:
            nested_buffer = io.BytesIO()
            with zipfile.ZipFile(nested_buffer, "w") as nested:
                nested.writestr("trace.network", sensitive_header)
                nested.writestr("screenshot.png", b"binary\x00content")

            archive = Path(temporary_directory) / "nested-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("data/resources.zip", nested_buffer.getvalue())

            errors = scan_file(archive)

            self.assertEqual(1, len(errors))
            self.assertIn("sensitive CI artifact content detected", errors[0])

    def test_sensitive_text_is_still_detected_inside_archive(self) -> None:
        sensitive_header = "Authorization: Bearer redacted-token"
        with TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "trace-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("trace.network", sensitive_header)

            errors = scan_file(archive)

            self.assertEqual(1, len(errors))
            self.assertIn("sensitive CI artifact content detected", errors[0])


if __name__ == "__main__":
    unittest.main()
