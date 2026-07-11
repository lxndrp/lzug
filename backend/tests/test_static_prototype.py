from __future__ import annotations

import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
PROTOTYPE_DIR = ROOT_DIR / "prototypes" / "pruefungsrunde-prototyp"
HTML_PATH = PROTOTYPE_DIR / "index.html"
JS_PATH = PROTOTYPE_DIR / "app.js"


class AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.stylesheets: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "id" in attributes and attributes["id"]:
            self.ids.add(attributes["id"])
        if tag == "link" and attributes.get("rel") == "stylesheet":
            href = attributes.get("href")
            if href:
                self.stylesheets.append(href)
        if tag == "script":
            src = attributes.get("src")
            if src:
                self.scripts.append(src)


class StaticPrototypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = HTML_PATH.read_text(encoding="utf-8")
        self.javascript = JS_PATH.read_text(encoding="utf-8")
        self.parser = AssetParser()
        self.parser.feed(self.html)

    def test_referenced_assets_exist(self) -> None:
        self.assertIn("styles.css", self.parser.stylesheets)
        self.assertIn("app.js", self.parser.scripts)
        for asset in (*self.parser.stylesheets, *self.parser.scripts):
            self.assertTrue((PROTOTYPE_DIR / asset).exists(), asset)

    def test_javascript_id_selectors_have_matching_html_elements(self) -> None:
        selector_ids = set(re.findall(r'querySelector\(["\']#([A-Za-z0-9_-]+)', self.javascript))
        generated_ids = {"confirm-plan", "reopen-plan"}
        literal_ids = selector_ids - generated_ids
        self.assertFalse(literal_ids - self.parser.ids)

    def test_all_primary_views_are_wired_to_navigation_buttons(self) -> None:
        for view in ("dashboard", "candidates", "members", "planning", "locations"):
            self.assertIn(f'id="{view}-view"', self.html)
            self.assertIn(f'data-view="{view}"', self.html)

    def test_javascript_has_valid_syntax_when_node_is_available(self) -> None:
        try:
            completed = subprocess.run(
                ["node", "--check", str(JS_PATH)],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            self.skipTest("Node.js is not installed.")

        self.assertEqual("", completed.stderr)
        self.assertEqual(0, completed.returncode, completed.stderr)


if __name__ == "__main__":
    unittest.main()
