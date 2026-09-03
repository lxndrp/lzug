from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_demo_media import check

ROOT = Path(__file__).resolve().parents[2]


class DemoMediaContractTests(unittest.TestCase):
    def test_media_contract_matches_synthetic_fixture_versions(self) -> None:
        self.assertEqual([], check(ROOT))

    def test_media_contract_rejects_fixture_drift_and_missing_alt_text(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "fixtures").mkdir()
            (root / "docs/media").mkdir(parents=True)
            (root / "fixtures/synthetic-fixtures.json").write_text(
                json.dumps({"version": 3, "revision": "fixture", "demo_matrix_version": "demo"}),
                encoding="utf-8",
            )
            (root / "docs/media/demo-screenshots.json").write_text(
                json.dumps({"screenshots": [{"id": "one", "path": "/"}]}),
                encoding="utf-8",
            )
            violations = check(root)

        self.assertTrue(any("fixture_catalog_version" in item for item in violations))
        self.assertTrue(any("id, path, file" in item for item in violations))
