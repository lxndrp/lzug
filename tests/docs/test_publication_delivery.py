"""Contracts for the static demo landing page and its gated delivery."""

from __future__ import annotations

import unittest
from pathlib import Path

from docs.publication import (
    PUBLICATION_BASE_URL,
    convert_handbook_links,
    convert_repository_links,
    handbook_route,
    public_url,
    publication_base_url,
)
from tests.delivery.workflow_contract import job_block, trigger_block, workflow_text

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
        script = (ROOT / "docs/publication/relearn/static/js/demo-warmup.js").read_text(
            encoding="utf-8"
        )
        browser_check = (ROOT / "frontend/publication-e2e/publication.spec.ts").read_text(
            encoding="utf-8"
        )
        playwright_config = (ROOT / "frontend/playwright.publication.config.ts").read_text(
            encoding="utf-8"
        )
        template = (ROOT / "docs/publication/relearn/layouts/home/article.html").read_text(
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
            ROOT / "docs/publication/relearn/layouts/partials/favicon.html"
        ).read_text(encoding="utf-8")

        self.assertTrue((ROOT / "brand/derived/favicon.svg").is_file())
        self.assertIn(
            "favicon.svg logo-mark-dark.svg",
            (ROOT / "scripts/build-frontend.sh").read_text(),
        )
        self.assertIn('rel="icon"', favicon_partial)
        self.assertIn('{{ "images/favicon.svg" | relURL }}', favicon_partial)
        self.assertIn('"images/favicon.svg"', (ROOT / "docs/publication.py").read_text())

    def test_productive_sources_have_a_documentation_owner(self) -> None:
        self.assertFalse((ROOT / "prototypes/publication").exists())
        for relative in (
            "content/index.md",
            "public-font.css",
            "relearn/assets/css/custom.css",
            "relearn/layouts/home/article.html",
            "relearn/layouts/partials/favicon.html",
            "relearn/static/js/demo-warmup.js",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / "docs/publication" / relative).is_file())

    def test_readme_uses_public_portal_entrypoints_for_reader_audiences(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for route in ("/", "/nutzen/", "/betreiben/", "/entwickeln/"):
            with self.subTest(route=route):
                self.assertIn(
                    f"https://lzug.repertoire.papaspyrou.name{route}",
                    readme,
                )
        for repository_link in (
            "docs/portal/betreiben.md",
            "docs/handbook/Nutzung.md",
            "docs/developers/index.md",
            "docs/migrations/wiki-2026-09-03.md",
        ):
            with self.subTest(repository_link=repository_link):
                self.assertNotIn(repository_link, readme)

    def test_generated_public_site_has_one_canonical_linkcheck_entry(self) -> None:
        config = (ROOT / ".lychee.toml").read_text(encoding="utf-8")
        taskfile = (ROOT / "Taskfile.yml").read_text(encoding="utf-8")
        workflow = workflow_text(".github/workflows/publication.yml")

        self.assertIn("timeout = 20", config)
        self.assertIn("max_retries = 2", config)
        self.assertIn("retry_wait_time = 2", config)
        self.assertIn('include_fragments = "full"', config)
        self.assertIn(r"^https://demo\\.example\\.invalid(?:/|$)", config)
        self.assertIn("docs:publication:linkcheck:", taskfile)
        self.assertIn("lychee --config .lychee.toml", taskfile)
        self.assertIn("task docs:publication:linkcheck", workflow)
        self.assertIn('".lychee.toml"', workflow)

    def test_repository_handbook_routes_are_rendered_without_a_wiki_checkout(self) -> None:
        self.assertEqual("/handbuch/", handbook_route(Path("Home.md")))
        self.assertEqual("/nutzen/grundbegriffe/", handbook_route(Path("Nutzung-Grundbegriffe.md")))
        self.assertEqual(
            "/betreiben/installation-und-konfiguration/",
            handbook_route(Path("Administration-Installation-und-Konfiguration.md")),
        )
        self.assertEqual(
            "[Nutzung](/nutzen/#details)",
            convert_handbook_links(
                "[Nutzung](Nutzung#details)",
                {"Home": "/handbuch/", "Nutzung": "/nutzen/"},
            ),
        )

    def test_publication_remaps_source_fragments_to_rendered_relearn_anchors(self) -> None:
        self.assertEqual(
            "[Qualität](/entwickeln/delivery/#vollständige-qualität)",
            convert_repository_links(
                "[Qualität](../delivery.md#vollstandige-qualitat)",
                Path("docs/developers/decisions/example.md"),
                {"docs/developers/delivery.md": "/entwickeln/delivery/"},
            ),
        )

    def test_pages_deployment_is_manual_fail_closed_and_cannot_enable_pages(self) -> None:
        workflow = workflow_text(".github/workflows/publication.yml")
        triggers = trigger_block(workflow)
        build = job_block(workflow, "build")
        deploy = job_block(workflow, "deploy")

        self.assertIn("BASE_URL: https://lzug.repertoire.papaspyrou.name", workflow)
        self.assertIn("DEMO_URL: ${{ vars.DEMO_URL || 'https://demo.example.invalid' }}", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("actions: read", workflow)
        self.assertIn("python3 -m demo.contract validate-url", build)
        self.assertIn("--canonical", build)
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
        self.assertIn("-- task docs:publication:check DEMO_URL=", build)
        self.assertIn("-- task docs:publication:linkcheck DEMO_URL=", build)
        self.assertNotIn("Checkout canonical Wiki", workflow)
        self.assertNotIn("WIKI_ROOT", workflow)
        self.assertIn("if: github.event_name == 'schedule'", build)
        self.assertIn("if: github.event_name != 'schedule'", build)
        self.assertIn('cron: "29 4 * * 1"', triggers)
        self.assertIn("paths: &publication-paths", triggers)
        self.assertIn('"docs/publication/**"', triggers)
        self.assertIn('"frontend/src/**"', triggers)
        self.assertIn('"frontend/tsconfig*.json"', triggers)
        self.assertIn("PLAYWRIGHT_BROWSER_CHANNEL: chrome", build)
        self.assertIn("npm --prefix frontend run test:publication", build)
        self.assertIn("npm --prefix frontend run test:publication:a11y", build)
        self.assertNotIn("--no-sandbox", build)


if __name__ == "__main__":
    unittest.main()
