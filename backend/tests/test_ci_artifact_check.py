from __future__ import annotations

import io
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock

from scripts.check_ci_artifacts import (
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_TEXT_BYTES,
    MAX_TRACE_MEMBER_BYTES,
    ScanBudget,
    scan_archive,
    scan_file,
)


class CiArtifactCheckTests(unittest.TestCase):
    def test_large_playwright_trace_is_scanned_without_size_error(self) -> None:
        trace = b"{}\n" * (MAX_TEXT_BYTES // 3 + 1)
        with TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "trace-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("test.trace", trace)

            self.assertEqual([], scan_file(archive))

    def test_sensitive_content_is_detected_in_large_playwright_trace(self) -> None:
        trace = (b"{}\n" * (MAX_TEXT_BYTES // 3 + 1)) + b'"set-cookie": "session=example"\n'
        with TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "trace-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("0-trace.trace", trace)

            errors = scan_file(archive)

            self.assertEqual(1, len(errors))
            self.assertIn("sensitive CI artifact content detected", errors[0])

    def test_trace_member_above_trace_limit_is_rejected(self) -> None:
        member = zipfile.ZipInfo("test.trace")
        member.file_size = MAX_TRACE_MEMBER_BYTES + 1
        archive = Mock()
        archive.infolist.return_value = [member]

        errors = scan_archive(archive, Path("trace-report.zip"), ScanBudget(), 0)

        self.assertEqual(1, len(errors))
        self.assertIn("archive member exceeds scan size limit", errors[0])

    def test_trace_members_still_obey_archive_scan_budget(self) -> None:
        members = [zipfile.ZipInfo("0-trace.trace"), zipfile.ZipInfo("1-trace.trace")]
        for member in members:
            member.file_size = MAX_TRACE_MEMBER_BYTES // 2 + 1
        archive = MagicMock()
        archive.infolist.return_value = members
        archive.open.return_value.__enter__.return_value.read.return_value = b"{}\n"

        errors = scan_archive(archive, Path("trace-report.zip"), ScanBudget(), 0)

        self.assertEqual(1, len(errors))
        self.assertIn("archive scan size limit exceeded", errors[0])

    def test_non_trace_member_keeps_regular_member_limit(self) -> None:
        report = b"{}\n" * (MAX_ARCHIVE_MEMBER_BYTES // 3 + 1)
        with TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "trace-report.zip"
            with zipfile.ZipFile(archive, "w") as outer:
                outer.writestr("report.json", report)

            errors = scan_file(archive)

            self.assertEqual(1, len(errors))
            self.assertIn("archive member exceeds scan size limit", errors[0])

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
