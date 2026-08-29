from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_documentation import (
    check,
    check_adrs,
    check_navigation,
    check_redundant_inventories,
)

ROOT = Path(__file__).resolve().parents[2]


class DocumentationContractTests(unittest.TestCase):
    def test_repository_documentation_has_no_structural_drift(self) -> None:
        self.assertEqual([], check(ROOT))

    def test_navigation_rejects_historical_pages_and_individual_adrs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs/developers/decisions").mkdir(parents=True)
            (root / "docs/history").mkdir()
            (root / "docs/index.md").write_text("# Start\n", encoding="utf-8")
            (root / "docs/developers/decisions/0001-test.md").write_text(
                "# ADR-0001: Test\n", encoding="utf-8"
            )
            (root / "mkdocs.yml").write_text(
                "nav:\n"
                "  - Start: index.md\n"
                "  - History: history/release-evidence.md\n"
                "  - ADR: developers/decisions/0001-test.md\n",
                encoding="utf-8",
            )

            violations = check_navigation(root)

        self.assertTrue(any("DOC-NAV-003" in violation for violation in violations))
        self.assertTrue(any("DOC-NAV-004" in violation for violation in violations))

    def test_inventory_and_duplicate_contracts_reject_negative_examples(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            docs = root / "docs"
            docs.mkdir()
            (docs / "bad.md").write_text(
                "# Bad\n\n"
                "## Issue-Inventar\n\n- #481\n- #482\n\n"
                "## API-Routen\n\n"
                "| Route |\n| --- |\n| GET /api/one |\n| GET /api/two |\n| GET /api/three |\n\n"
                "## Schema-Feldliste\n\n"
                "| Name | Typ |\n| --- | --- |\n| one | text |\n| two | text |\n| three | text |\n",
                encoding="utf-8",
            )

            violations = check_redundant_inventories(root)

        self.assertTrue(any("DOC-CONTENT-001" in violation for violation in violations))
        self.assertTrue(any("DOC-CONTENT-002" in violation for violation in violations))
        self.assertTrue(any("DOC-CONTENT-003" in violation for violation in violations))

    def test_adr_requires_status_and_keeps_supersession_in_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            decisions = root / "docs/developers/decisions"
            decisions.mkdir(parents=True)
            (decisions / "index.md").write_text(
                "[0001](0001-first.md)\n[0002](0002-second.md)\n", encoding="utf-8"
            )
            (decisions / "0001-first.md").write_text(
                "# ADR-0001: First\n\n## Status\n\n"
                "Akzeptiert am 2026-08-29. Superseded by: ADR-0002.\n",
                encoding="utf-8",
            )
            (decisions / "0002-second.md").write_text(
                "# ADR-0002: Second\n\n## Status\n\nAkzeptiert am 2026-08-29.\n\n"
                "## Kontext\n\nSupersedes: ADR-0001.\n",
                encoding="utf-8",
            )

            violations = check_adrs(root)

        self.assertTrue(any("DOC-ADR-005" in violation for violation in violations))

    def test_adr_status_and_index_are_valid_for_positive_example(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            decisions = root / "docs/developers/decisions"
            decisions.mkdir(parents=True)
            (decisions / "index.md").write_text(
                "[0001](0001-first.md)\n[0002](0002-second.md)\n", encoding="utf-8"
            )
            (decisions / "0001-first.md").write_text(
                "# ADR-0001: First\n\n## Status\n\n"
                "Akzeptiert am 2026-08-29. Superseded by: ADR-0002.\n",
                encoding="utf-8",
            )
            (decisions / "0002-second.md").write_text(
                "# ADR-0002: Second\n\n## Status\n\n"
                "Akzeptiert am 2026-08-29. Supersedes: ADR-0001.\n",
                encoding="utf-8",
            )

            violations = check_adrs(root)

        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
