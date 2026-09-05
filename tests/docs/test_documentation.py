from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_documentation import (
    HANDBOOK_FILES,
    check,
    check_adrs,
    check_developer_structure,
    check_handbook,
    check_navigation,
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
            (root / "docs/mkdocs.yml").parent.mkdir(parents=True, exist_ok=True)
            (root / "docs/mkdocs.yml").write_text(
                "nav:\n"
                "  - Start: index.md\n"
                "  - History: history/release-evidence.md\n"
                "  - ADR: developers/decisions/0001-test.md\n",
                encoding="utf-8",
            )

            violations = check_navigation(root)

        self.assertTrue(any("DOC-NAV-003" in violation for violation in violations))
        self.assertTrue(any("DOC-NAV-004" in violation for violation in violations))

    def test_developer_structure_rejects_legacy_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            developers = root / "docs/developers"
            decisions = developers / "decisions"
            reference = developers / "reference"
            decisions.mkdir(parents=True)
            reference.mkdir()
            for filename in (
                "architecture.md",
                "components.md",
                "data-and-contracts.md",
                "delivery.md",
                "development.md",
                "index.md",
                "script-inventory.md",
            ):
                (developers / filename).write_text(f"# {filename}\n", encoding="utf-8")
            (decisions / "index.md").write_text("# Decisions\n", encoding="utf-8")
            (decisions / "TEMPLATE.md").write_text("# Template\n", encoding="utf-8")
            (reference / "backend.md").write_text("# Backend\n", encoding="utf-8")
            (reference / "cli.md").write_text("# CLI\n", encoding="utf-8")
            (reference / "frontend.md").write_text("# Frontend\n", encoding="utf-8")
            (reference / "full-export-v1.schema.json").write_text("{}\n", encoding="utf-8")
            (developers / "legacy.md").write_text("# Legacy\n", encoding="utf-8")

            violations = check_developer_structure(root)

        self.assertTrue(any("DOC-STRUCT-003" in violation for violation in violations))

    def test_handbook_check_only_requires_the_current_documentation_set(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            handbook = root / "docs/handbook"
            handbook.mkdir(parents=True)
            for filename in HANDBOOK_FILES:
                (handbook / filename).write_text(f"# {filename}\n", encoding="utf-8")

            violations = check_handbook(root)

        self.assertEqual([], violations)

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
