"""Contracts for the static demo landing page and its gated delivery."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.publication_spike import public_url

ROOT = Path(__file__).resolve().parents[2]


class PublicationDeliveryContractTests(unittest.TestCase):
    def test_public_urls_are_https_and_demo_url_is_an_origin(self) -> None:
        self.assertEqual(
            "https://lxndrp.github.io/lzug",
            public_url("https://lxndrp.github.io/lzug/", allow_path=True),
        )
        self.assertEqual(
            "https://demo.example.invalid",
            public_url("https://demo.example.invalid/", allow_path=False),
        )
        for invalid in (
            "http://demo.example.invalid",
            "https://user@demo.example.invalid",
            "https://demo.example.invalid/path",
            "https://demo.example.invalid?token=value",
            "https://demo.example.invalid/#fragment",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                public_url(invalid, allow_path=False)

    def test_warm_up_is_bounded_and_sends_no_credentials_or_referrer(self) -> None:
        script = (ROOT / "prototypes/publication/relearn/static/js/demo-warmup.js").read_text(
            encoding="utf-8"
        )
        template = (ROOT / "prototypes/publication/relearn/layouts/home/article.html").read_text(
            encoding="utf-8"
        )

        self.assertIn('data-demo-maximum-attempts="12"', template)
        self.assertIn('data-demo-total-timeout-ms="90000"', template)
        self.assertIn('credentials: "omit"', script)
        self.assertIn('referrerPolicy: "no-referrer"', script)
        self.assertIn('redirect: "error"', script)
        self.assertIn("`${demoUrl}/api/health`", script)
        self.assertIn('button.textContent = "Erneut versuchen"', script)

    def test_pages_deployment_is_manual_fail_closed_and_cannot_enable_pages(self) -> None:
        workflow = (ROOT / ".github/workflows/publication.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/master"', workflow)
        self.assertIn('test "$CONFIRM_PUBLICATION" = "true"', workflow)
        self.assertIn("github.event_name == 'workflow_dispatch'", workflow)
        self.assertIn("pages: write", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("environment:\n      name: github-pages", workflow)
        self.assertIn("actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d", workflow)
        self.assertIn("enablement: false", workflow)
        self.assertEqual(
            2,
            workflow.count("mise x hugo-extended@0.165.0 -- task docs:publication"),
        )
        self.assertNotIn("run: task docs:publication", workflow)
        self.assertNotIn("schedule:", workflow)


if __name__ == "__main__":
    unittest.main()
