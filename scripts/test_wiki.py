import tempfile
import unittest
from pathlib import Path

from scripts.check_wiki import (
    check_sidebar_routes,
    markdown_files,
    write_routes,
)
from scripts.publication import convert_wiki_links
from scripts.wiki_routes import wiki_route, wiki_source_url


class WikiValidatorTests(unittest.TestCase):
    def create_candidate(self, root: Path) -> None:
        for page in ("Home", "Fachlichkeit", "Nutzung"):
            (root / f"{page}.md").write_text(f"# {page}\n", encoding="utf-8")
        (root / "Home.md").write_text("[Fachlichkeit](Fachlichkeit)\n", encoding="utf-8")
        (root / "_Sidebar.md").write_text(
            "- [Home](Home)\n- [Fachlichkeit](Fachlichkeit)\n- [Nutzung](Nutzung)\n",
            encoding="utf-8",
        )

    def test_sidebar_complete_candidate_creates_deterministic_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            pages, errors = check_sidebar_routes(root, markdown_files(root))
            self.assertEqual([], errors)
            routes = root / "temporary" / "routes.md"
            write_routes(routes, pages, "https://example.test/wiki")
            self.assertEqual(
                "- <https://example.test/wiki/Fachlichkeit>\n"
                "- <https://example.test/wiki>\n"
                "- <https://example.test/wiki/Nutzung>\n",
                routes.read_text(encoding="utf-8"),
            )

    def test_shared_route_contract_derives_publication_names(self):
        self.assertEqual(
            ("Handbuch", "_index.md", "/handbuch/"),
            (
                wiki_route("Home").title,
                wiki_route("Home").publication_file,
                wiki_route("Home").publication_route,
            ),
        )
        self.assertEqual(
            "https://example.test/wiki/Fachlichkeit",
            wiki_source_url("Fachlichkeit", "https://example.test/wiki/"),
        )
        self.assertEqual(
            "[Fachlichkeit](/handbuch/fachlichkeit/#details)",
            convert_wiki_links("[Fachlichkeit](Fachlichkeit#details)", {"Home", "Fachlichkeit"}),
        )
        self.assertEqual(
            ("Fachlichkeit", "fachlichkeit.md", "/handbuch/fachlichkeit/"),
            (
                wiki_route("Fachlichkeit").title,
                wiki_route("Fachlichkeit").publication_file,
                wiki_route("Fachlichkeit").publication_route,
            ),
        )

    def test_orphan_content_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "Verwaist.md").write_text("# Verwaist\n", encoding="utf-8")
            _, errors = check_sidebar_routes(root, markdown_files(root))
            self.assertIn(
                "wiki: content page is missing from _Sidebar.md: Verwaist",
                errors,
            )

    def test_missing_or_duplicate_sidebar_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "_Sidebar.md").write_text(
                "- [Home](Home)\n- [Home again](Home)\n- [Missing](Missing)\n"
                "- [Fachlichkeit](Fachlichkeit)\n- [Nutzung](Nutzung)\n",
                encoding="utf-8",
            )
            _, errors = check_sidebar_routes(root, markdown_files(root))
            self.assertIn("wiki: sidebar target is duplicated: Home", errors)
            self.assertIn("wiki: sidebar target does not exist: Missing", errors)

    def test_raw_markdown_sidebar_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "_Sidebar.md").write_text(
                "- [Home](Home.md)\n- [Fachlichkeit](Fachlichkeit)\n- [Nutzung](Nutzung)\n",
                encoding="utf-8",
            )
            _, errors = check_sidebar_routes(root, markdown_files(root))
            self.assertTrue(any("extensionless flat page" in error for error in errors))

    def test_nested_content_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            nested = root / "nested"
            nested.mkdir()
            (nested / "Details.md").write_text("# Details\n", encoding="utf-8")
            _, errors = check_sidebar_routes(root, markdown_files(root))
            self.assertIn("wiki: page must be flat: nested/Details.md", errors)


if __name__ == "__main__":
    unittest.main()
