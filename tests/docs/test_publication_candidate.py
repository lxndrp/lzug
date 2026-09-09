"""Contracts for the unactivated Wiki and reduced Pages migration candidates."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from docs.publication import (
    EXPECTED_OUTPUTS,
    WIKI_BASE_URL,
    build_wiki_candidate,
    candidate_product_content,
    check_wiki_candidate,
    publication_inventory,
    stable_version,
    validate_rollback_candidate,
    wiki_source_files,
    write_wiki_routes,
)

ROOT = Path(__file__).resolve().parents[2]


class PublicationCandidateContractTests(unittest.TestCase):
    def test_wiki_candidate_is_flat_complete_versioned_and_reproducible(self) -> None:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as temporary:
            first = Path(temporary) / "first"
            second = Path(temporary) / "second"
            build_wiki_candidate(ROOT, first, revision)
            build_wiki_candidate(ROOT, second, revision)

            self.assertEqual([], check_wiki_candidate(first, stable_version(ROOT)))
            self.assertEqual(
                sorted(path.name for path in first.iterdir()),
                sorted(path.name for path in second.iterdir()),
            )
            for source in wiki_source_files(ROOT):
                self.assertTrue((first / source.name).is_file())
                self.assertEqual(
                    (first / source.name).read_bytes(),
                    (second / source.name).read_bytes(),
                )
            self.assertFalse(any(path.name.startswith("Entwicklung") for path in first.iterdir()))
            self.assertIn(
                f"aktuellen stabilen Stand lzug {stable_version(ROOT)}",
                (first / "Home.md").read_text(encoding="utf-8"),
            )

    def test_wiki_validator_rejects_nested_raw_missing_and_orphan_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "nested").mkdir()
            (root / "Home.md").write_text("# Home\n\n[Raw](Missing.md)\n", encoding="utf-8")
            (root / "Versionshinweise.md").write_text("# Version\n", encoding="utf-8")
            (root / "Orphan.md").write_text("# Orphan\n", encoding="utf-8")
            (root / "nested/Details.md").write_text("# Details\n", encoding="utf-8")
            (root / "_Sidebar.md").write_text(
                "- [Home](Home)\n- [Missing](Missing)\n- [Raw](Versionshinweise.md)\n",
                encoding="utf-8",
            )

            errors = check_wiki_candidate(root)

        self.assertTrue(any("page must be flat" in error for error in errors))
        self.assertTrue(any("extensionless and flat" in error for error in errors))
        self.assertTrue(any("target does not exist: Missing" in error for error in errors))
        self.assertTrue(any("missing from _Sidebar.md: Orphan" in error for error in errors))

    def test_wiki_validator_ignores_git_metadata_from_a_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git").mkdir()
            (root / ".git/config").write_text("[core]\n", encoding="utf-8")
            (root / "Home.md").write_text("# Home\n", encoding="utf-8")
            (root / "Versionshinweise.md").write_text("# Version\n", encoding="utf-8")
            (root / "_Sidebar.md").write_text(
                "- [Home](Home)\n- [Version](Versionshinweise)\n",
                encoding="utf-8",
            )

            errors = check_wiki_candidate(root)

        self.assertEqual([], errors)

    def test_wiki_routes_are_derived_from_sidebar_without_redirect_tolerance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("Home.md", "Versionshinweise.md"):
                (root / name).write_text(f"# {name}\n", encoding="utf-8")
            (root / "_Sidebar.md").write_text(
                "- [Home](Home)\n- [Version](Versionshinweise)\n", encoding="utf-8"
            )
            routes = Path(temporary) / "routes.md"
            write_wiki_routes(root, routes, WIKI_BASE_URL)

            self.assertEqual(
                f"- <{WIKI_BASE_URL}>\n- <{WIKI_BASE_URL}/Versionshinweise>\n",
                routes.read_text(encoding="utf-8"),
            )

    def test_reduced_product_content_labels_cross_surface_links(self) -> None:
        revision = "a" * 40
        transformed = candidate_product_content(
            "[Nutzung](/nutzen/) [Betrieb](/betreiben/) [Entwicklung](/entwickeln/)",
            revision,
        )

        self.assertIn(f"{WIKI_BASE_URL}/Nutzung", transformed)
        self.assertIn(f"{WIKI_BASE_URL}/Administration", transformed)
        self.assertIn(f"/blob/{revision}/docs/developers/index.md", transformed)
        self.assertNotIn("](/nutzen/)", transformed)
        self.assertNotIn("](/betreiben/)", transformed)
        self.assertNotIn("](/entwickeln/)", transformed)

    def test_generated_inventory_covers_all_source_classes_and_controlled_entries(self) -> None:
        inventory = publication_inventory(ROOT, "b" * 40)
        sources = {item["source"] for item in inventory}

        self.assertIn("docs/handbook/Home.md", sources)
        self.assertIn("docs/handbook/Entwicklung.md", sources)
        self.assertIn("docs/portal/produkt.md", sources)
        self.assertIn("docs/developers/index.md", sources)
        self.assertIn("backend OpenAPI assembly", sources)
        self.assertIn("backend/db/schema.sql", sources)
        self.assertIn("README.md", sources)
        self.assertIn("frontend/src/app/dashboard/dashboard.component.ts", sources)
        self.assertFalse((ROOT / "docs/migrations").exists())

    def test_rollback_check_binds_pages_manifest_and_wiki_commit(self) -> None:
        repository_revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            pages = temporary_root / "pages"
            wiki = temporary_root / "wiki"
            pages.mkdir()
            wiki.mkdir()
            for relative in EXPECTED_OUTPUTS:
                target = pages / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("", encoding="utf-8")
            (pages / "quellen.json").write_text(
                json.dumps({"repository_revision": repository_revision}), encoding="utf-8"
            )
            subprocess.run(["git", "init", "-q"], cwd=wiki, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=wiki, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"], cwd=wiki, check=True
            )
            (wiki / "Home.md").write_text("# Previous Wiki\n", encoding="utf-8")
            subprocess.run(["git", "add", "Home.md"], cwd=wiki, check=True)
            subprocess.run(["git", "commit", "-q", "-m", "Previous Wiki"], cwd=wiki, check=True)
            wiki_revision = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=wiki,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = validate_rollback_candidate(
                ROOT, pages, repository_revision, wiki, wiki_revision
            )

        self.assertIn(f"repository={repository_revision}", result)
        self.assertIn(f"wiki={wiki_revision}", result)

    def test_render_check_uses_gollum_and_requires_nonempty_pages(self) -> None:
        checker = (ROOT / "docs/publication/check-wiki-render.rb").read_text(encoding="utf-8")

        self.assertIn('require "gollum-lib"', checker)
        self.assertIn("page.formatted_data", checker)
        self.assertIn("page rendered empty", checker)

    def test_pages_rollback_route_is_sha_bound_and_keeps_the_environment_gate(self) -> None:
        workflow = (ROOT / ".github/workflows/publication.yml").read_text(encoding="utf-8")

        self.assertIn("repository_revision:", workflow)
        self.assertIn('test "${#target}" -eq 40', workflow)
        self.assertIn("*[!0-9a-f]*)", workflow)
        self.assertIn('git merge-base --is-ancestor "$target" origin/master', workflow)
        self.assertIn('git checkout --detach "$target"', workflow)
        self.assertIn("task docs:publication:candidate:check", workflow)
        self.assertIn("name: publication-migration-candidates", workflow)
        self.assertGreaterEqual(workflow.count("include-hidden-files: true"), 2)
        self.assertIn("environment:\n      name: github-pages", workflow)
        self.assertIn("enablement: false", workflow)


if __name__ == "__main__":
    unittest.main()
