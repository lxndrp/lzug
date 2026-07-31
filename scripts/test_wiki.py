import tempfile
import unittest
from pathlib import Path

from scripts.check_wiki import (
    check_internal_wiki_route_syntax,
    check_public_safety,
    check_structure,
    markdown_files,
    write_sitemap,
)


class WikiValidatorTests(unittest.TestCase):
    def create_candidate(self, root: Path) -> None:
        for page in ("Home", "Fachlichkeit", "Nutzung"):
            (root / f"{page}.md").write_text(f"# {page}\n", encoding="utf-8")
        (root / "Home.md").write_text("[Fachlichkeit](Fachlichkeit)\n", encoding="utf-8")
        (root / "_Sidebar.md").write_text(
            "- [Home](Home)\n- [Fachlichkeit](Fachlichkeit)\n- [Nutzung](Nutzung)\n",
            encoding="utf-8",
        )

    def test_sidebar_complete_candidate_creates_deterministic_sitemap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            files = markdown_files(root)
            self.assertEqual([], check_structure(root, files))
            sitemap = root / "temporary" / "sitemap.xml"
            write_sitemap(sitemap, {"Nutzung", "Home", "Fachlichkeit"}, "https://example.test/wiki")
            self.assertEqual(
                "<?xml version='1.0' encoding='utf-8'?>\n"
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                "<url><loc>https://example.test/wiki/Fachlichkeit</loc></url>"
                "<url><loc>https://example.test/wiki</loc></url>"
                "<url><loc>https://example.test/wiki/Nutzung</loc></url>"
                "</urlset>",
                sitemap.read_text(encoding="utf-8"),
            )

    def test_orphan_content_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "Verwaist.md").write_text("# Verwaist\n", encoding="utf-8")
            self.assertIn(
                "wiki: content page is missing from _Sidebar.md: Verwaist",
                check_structure(root, markdown_files(root)),
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
            errors = check_structure(root, markdown_files(root))
            self.assertIn("wiki: sidebar target is duplicated: Home", errors)
            self.assertIn("wiki: sidebar target does not exist: Missing", errors)

    def test_raw_markdown_route_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "Home.md").write_text("[Fachlichkeit](Fachlichkeit.md)\n", encoding="utf-8")
            errors = check_internal_wiki_route_syntax(markdown_files(root))
            self.assertTrue(any("must be extensionless" in error for error in errors))

    def test_secret_like_content_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "Home.md").write_text("api_key: not-for-publication\n", encoding="utf-8")
            errors = check_public_safety(markdown_files(root))
            self.assertTrue(any("secret-like content detected" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
