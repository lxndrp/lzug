from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.generate_frontend_transport import changed_paths, replace_generated


class FrontendTransportGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.candidate = self.root / "candidate"
        self.target = self.root / "target"
        self.candidate.mkdir()
        self.target.mkdir()

    def test_changed_paths_reports_missing_stale_and_unexpected_files(self) -> None:
        (self.candidate / "missing.ts").write_text("expected\n", encoding="utf-8")
        (self.candidate / "stale.ts").write_text("expected\n", encoding="utf-8")
        (self.target / "stale.ts").write_text("actual\n", encoding="utf-8")
        (self.target / "unexpected.ts").write_text("unexpected\n", encoding="utf-8")

        self.assertEqual(
            changed_paths(self.candidate, self.target),
            [Path("missing.ts"), Path("stale.ts"), Path("unexpected.ts")],
        )

    def test_replace_generated_only_reconciles_the_target_directory(self) -> None:
        nested = self.candidate / "nested"
        nested.mkdir()
        (nested / "types.gen.ts").write_text("generated\n", encoding="utf-8")
        (self.target / "obsolete.ts").write_text("obsolete\n", encoding="utf-8")
        sibling = self.root / "handwritten.ts"
        sibling.write_text("handwritten\n", encoding="utf-8")

        replace_generated(self.candidate, self.target)

        self.assertEqual(changed_paths(self.candidate, self.target), [])
        self.assertFalse((self.target / "obsolete.ts").exists())
        self.assertEqual(sibling.read_text(encoding="utf-8"), "handwritten\n")


if __name__ == "__main__":
    unittest.main()
