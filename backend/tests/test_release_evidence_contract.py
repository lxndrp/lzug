from __future__ import annotations

import re
import tomllib
import unittest
from pathlib import Path

from scripts.release import extract_changelog


class ReleaseEvidenceContractTests(unittest.TestCase):
    def test_v0_1_0_changelog_is_unique_dated_nonempty_and_scoped(self) -> None:
        changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")

        self.assertEqual(
            1, len(re.findall(r"^## \[0\.1\.0\] - \d{4}-\d{2}-\d{2}$", changelog, re.MULTILINE))
        )
        section = extract_changelog(changelog, "0.1.0")
        compact_section = " ".join(section.split())
        for boundary in (
            "weder ein fachlich vollständiges noch ein produktionsreifes",
            "Upgrade, allgemeines Backup und Restore sowie Produkt-Rollback",
            "realer Pilot",
            "CycloneDX-SBOM",
        ):
            with self.subTest(boundary=boundary):
                self.assertIn(boundary, compact_section)
        self.assertNotIn("Bei einer Release-Vorbereitung", section)

    def test_operational_evidence_separates_tested_limits_from_unsupported_paths(self) -> None:
        evidence = Path("docs/developers/release-evidence-v0.1.0.md").read_text(encoding="utf-8")

        self.assertIn("backend.database.DEFAULT_MIN_FREE_BYTES", evidence)
        self.assertIn("64 MiB", evidence)
        self.assertIn("keine unterstützte quantitative Mindest- oder Referenz-CPU", evidence)
        self.assertIn("keine unterstützte quantitative Mindest- oder Referenz-RAM", evidence)
        self.assertIn("Release-Recovery", evidence)
        self.assertIn("kein Produkt-Rollback", evidence)
        self.assertIn("für `v0.6.0` geplant", evidence)

    def test_project_documentation_and_privacy_boundaries_are_consistent(self) -> None:
        metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual("AGPL-3.0-or-later", metadata["project"]["license"])

        documentation_license = Path("docs/LICENSE.md").read_text(encoding="utf-8")
        privacy = Path("docs/developers/privacy.md").read_text(encoding="utf-8")
        notices = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        compact_privacy = " ".join(privacy.split())
        self.assertIn("CC-BY-4.0", documentation_license)
        self.assertIn("AGPL-3.0-or-later", documentation_license)
        self.assertIn("nicht als allgemeine Datenschutzkonformität", compact_privacy)
        self.assertIn("manual-review-required", notices)


if __name__ == "__main__":
    unittest.main()
