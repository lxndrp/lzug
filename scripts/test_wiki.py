import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError

from scripts.check_wiki import REQUIRED_PAGES, check_links, check_structure, markdown_files
from scripts.check_wiki_http import check_page


class WikiValidatorTests(unittest.TestCase):
    def create_candidate(self, root: Path) -> None:
        for page in REQUIRED_PAGES:
            (root / page).write_text(f"# {page}\n", encoding="utf-8")
        root_pages = ("Fachlichkeit", "Nutzung", "Administration", "Entwicklung")
        (root / "Home.md").write_text(
            "\n".join(f"- [{page}]({page})" for page in root_pages) + "\n",
            encoding="utf-8",
        )
        sidebar_pages = ("Home", "Fachlichkeit", "Nutzung", "Administration", "Entwicklung")
        (root / "_Sidebar.md").write_text(
            "\n".join(f"- [{page}]({page})" for page in sidebar_pages) + "\n",
            encoding="utf-8",
        )

    def test_flat_extensionless_candidate_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            files = markdown_files(root)
            self.assertEqual([], check_structure(root, files))
            self.assertEqual([], check_links(root, files))

    def test_nested_page_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            nested = root / "Fachlichkeit" / "index.md"
            nested.parent.mkdir()
            nested.write_text("# nested\n", encoding="utf-8")
            errors = check_structure(root, markdown_files(root))
            self.assertIn("wiki: page must be flat: Fachlichkeit/index.md", errors)

    def test_internal_markdown_link_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_candidate(root)
            (root / "Home.md").write_text("[Fachlichkeit](Fachlichkeit.md)\n", encoding="utf-8")
            errors = check_links(root, markdown_files(root))
            self.assertTrue(any("must be extensionless" in error for error in errors))


class WikiHttpCheckTests(unittest.TestCase):
    def test_github_home_redirect_is_checked_at_canonical_root(self):
        redirect_headers = Message()
        redirect_headers["Location"] = "https://github.com/wiki"
        redirect = HTTPError(
            "https://github.com/wiki/Home", 301, "Moved Permanently", redirect_headers, None
        )
        response = Mock(status=200, getcode=lambda: 200, geturl=lambda: "https://github.com/wiki")
        headers = Message()
        headers["Content-Type"] = "text/html"
        response.headers = headers
        response.close = Mock()
        opener = Mock()
        opener.open.side_effect = [redirect, response]
        self.assertEqual([], check_page(opener, "https://github.com/wiki", "Home"))

    def test_rendered_page_requires_html(self):
        response = Mock(
            status=200, getcode=lambda: 200, geturl=lambda: "https://github.com/wiki/Home"
        )
        headers = Message()
        headers["Content-Type"] = "text/plain"
        response.headers = headers
        response.close = Mock()
        opener = Mock()
        opener.open.return_value = response
        self.assertEqual(
            ["Home: expected Content-Type text/html, got text/plain"],
            check_page(opener, "https://github.com/wiki", "Home"),
        )

    def test_raw_redirect_is_rejected(self):
        headers = Message()
        headers["Location"] = "https://raw.githubusercontent.com/lxndrp/lzug.wiki/master/Home.md"
        opener = Mock()
        opener.open.side_effect = HTTPError(
            "https://github.com/wiki/Home", 302, "Found", headers, None
        )
        errors = check_page(opener, "https://github.com/wiki", "Home")
        self.assertTrue(any("raw.githubusercontent.com" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
