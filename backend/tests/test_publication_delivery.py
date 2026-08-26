"""Contracts for the static demo landing page and its gated delivery."""

from __future__ import annotations

import unittest
from pathlib import Path

from backend.tests.workflow_contract import job_block, trigger_block, workflow_text
from scripts.publication_spike import PUBLICATION_BASE_URL, public_url, publication_base_url

ROOT = Path(__file__).resolve().parents[2]


class PublicationDeliveryContractTests(unittest.TestCase):
    def test_public_urls_are_https_and_demo_url_is_an_origin(self) -> None:
        self.assertEqual(
            PUBLICATION_BASE_URL,
            publication_base_url("https://lzug.repertoire.papaspyrou.name/"),
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
            "https://stage.papaspyrou.name/lzug/",
            "https://*.repertoire.papaspyrou.name",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                public_url(invalid, allow_path=False)

        with self.assertRaises(ValueError):
            publication_base_url("https://stage.papaspyrou.name/lzug/")

    def test_warm_up_is_bounded_and_sends_no_credentials_or_referrer(self) -> None:
        script = (ROOT / "prototypes/publication/relearn/static/js/demo-warmup.js").read_text(
            encoding="utf-8"
        )
        browser_check = (ROOT / "frontend/publication-e2e/publication.spec.ts").read_text(
            encoding="utf-8"
        )
        playwright_config = (ROOT / "frontend/playwright.publication.config.ts").read_text(
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
        self.assertIn("`${demoUrl}/api/ready`", script)
        self.assertNotIn("`${demoUrl}/api/health`", script)
        self.assertIn('payload.status === "ready"', script)
        self.assertIn('button.textContent = "Erneut versuchen"', script)
        self.assertIn("chromiumSandbox: true", playwright_config)
        self.assertIn("browserChannel !== 'chrome'", playwright_config)
        self.assertIn("video: 'off'", playwright_config)
        self.assertIn("getAttribute('data-demo-url')", browser_check)
        self.assertIn("expect(configuredValue).toBe(configuredUrl.origin)", browser_check)
        self.assertIn("`${warmupDemoOrigin}/api/ready`", browser_check)
        self.assertIn("`${warmupDemoOrigin}/`", browser_check)
        self.assertIn("`${failureDemoOrigin}/api/ready`", browser_check)
        self.assertEqual(2, browser_check.count("route.abort('blockedbyclient')"))
        self.assertIn("expect(failedReadinessRequests).toBe(2)", browser_check)
        self.assertNotIn("demo.example.invalid", browser_check)
        self.assertNotIn("DEMO_URL", browser_check)
        self.assertNotIn("/lzug/", browser_check)

    def test_favicon_uses_the_publication_base_path_and_existing_product_asset(self) -> None:
        favicon_partial = (
            ROOT / "prototypes/publication/relearn/layouts/partials/favicon.html"
        ).read_text(encoding="utf-8")

        self.assertTrue((ROOT / "frontend/public/favicon.svg").is_file())
        self.assertIn('rel="icon"', favicon_partial)
        self.assertIn('{{ "images/favicon.svg" | relURL }}', favicon_partial)
        self.assertIn('"images/favicon.svg"', (ROOT / "scripts/publication_spike.py").read_text())

    def test_pages_deployment_is_manual_fail_closed_and_cannot_enable_pages(self) -> None:
        workflow = workflow_text(".github/workflows/publication.yml")
        triggers = trigger_block(workflow)
        build = job_block(workflow, "build")
        deploy = job_block(workflow, "deploy")

        self.assertIn("BASE_URL: https://lzug.repertoire.papaspyrou.name", workflow)
        self.assertIn("DEMO_URL: ${{ vars.DEMO_URL || 'https://demo.example.invalid' }}", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("actions: read", workflow)
        self.assertIn("scripts/validate_demo_url_contract.py validate", build)
        self.assertIn('--value "$EFFECTIVE_DEMO_URL"', build)
        self.assertIn("EFFECTIVE_DEMO_URL", build)
        self.assertNotIn("GH_TOKEN", workflow)
        self.assertNotIn("github.token", workflow)
        self.assertNotIn("--repository", workflow)
        validator = (ROOT / "scripts/validate_demo_url_contract.py").read_text(encoding="utf-8")
        self.assertNotIn("actions/variables", validator)
        self.assertNotIn("api.github.com", validator)
        self.assertNotIn("urlopen", validator)
        self.assertNotIn("urllib", validator)
        self.assertNotIn("GH_TOKEN", validator)
        self.assertNotIn("azurecontainerapps.io", workflow)
        self.assertNotIn("stage.papaspyrou.name", workflow)
        self.assertIn("pull_request:", triggers)
        self.assertIn("push:", triggers)
        self.assertIn("schedule:", triggers)
        self.assertIn("workflow_dispatch:", triggers)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/master"', build)
        self.assertNotIn("confirm_publication", workflow)
        self.assertNotIn("CONFIRM_PUBLICATION", workflow)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", deploy)
        self.assertIn("needs: build", deploy)
        self.assertIn("pages: write", deploy)
        self.assertIn("id-token: write", deploy)
        self.assertIn("environment:\n      name: github-pages", deploy)
        self.assertIn("actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d", deploy)
        self.assertIn("enablement: false", deploy)
        self.assertIn("-- task docs:publication:check WIKI_ROOT=", build)
        self.assertIn("-- task docs:publication WIKI_ROOT=", build)
        self.assertIn("if: github.event_name == 'schedule'", build)
        self.assertIn("if: github.event_name != 'schedule'", build)
        self.assertIn('cron: "29 4 * * 1"', triggers)
        self.assertIn("paths: &publication-paths", triggers)
        self.assertIn('"prototypes/publication/**"', triggers)
        self.assertIn('"frontend/src/**"', triggers)
        self.assertIn('"frontend/tsconfig*.json"', triggers)
        self.assertIn("PLAYWRIGHT_BROWSER_CHANNEL: chrome", build)
        self.assertIn("npm --prefix frontend run test:publication", build)
        self.assertIn("npm --prefix frontend run test:publication:a11y", build)
        self.assertNotIn("--no-sandbox", build)

    def test_wiki_post_publish_check_is_periodic_manual_diagnostics(self) -> None:
        workflow = workflow_text(".github/workflows/wiki-post-publish.yml")
        triggers = trigger_block(workflow)
        check = job_block(workflow, "check")

        self.assertIn("schedule:", triggers)
        self.assertIn("workflow_dispatch:", triggers)
        self.assertIn('cron: "43 5 * * 1"', triggers)
        self.assertNotIn("gollum:", triggers)
        self.assertNotIn("pull_request:", triggers)
        self.assertNotIn("push:", triggers)
        self.assertIn("scripts/check_wiki.py published-wiki", check)
        self.assertIn("--max-redirects 0", check)


if __name__ == "__main__":
    unittest.main()
