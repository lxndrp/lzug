"""Contracts for the checked-in Hugo publication project and its delivery."""

from __future__ import annotations

import unittest
from pathlib import Path

from tests.delivery.workflow_contract import job_block, trigger_block, workflow_text

ROOT = Path(__file__).resolve().parents[2]


class PublicationDeliveryContractTests(unittest.TestCase):
    def test_theme_is_a_concrete_blowfish_v3_pin(self) -> None:
        config = (ROOT / "docs/publication/hugo.toml").read_text()
        module = (ROOT / "docs/publication/go.mod").read_text()
        self.assertIn("theme = 'github.com/nunocoracao/blowfish/v3'", config)
        self.assertIn("blowfishVersion = 'v3.6.0'", config)
        self.assertIn("blowfishRevision = '4643c46bd5e921fee51c420575fadebf9f4b3681'", config)
        self.assertIn("github.com/nunocoracao/blowfish/v3 v3.6.0", module)
        self.assertFalse((ROOT / "docs/publication.py").exists())
        self.assertFalse((ROOT / "docs/publication/relearn").exists())

    def test_warm_up_is_bounded_and_sends_no_credentials_or_referrer(self) -> None:
        script = (ROOT / "docs/publication/blowfish/static/js/demo-warmup.js").read_text()
        browser_check = (ROOT / "frontend/publication-e2e/publication.spec.ts").read_text()
        playwright_config = (ROOT / "frontend/playwright.publication.config.ts").read_text()
        template = (ROOT / "docs/publication/blowfish/layouts/index.html").read_text()
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
        self.assertEqual(2, browser_check.count("route.abort('blockedbyclient')"))
        self.assertNotIn("demo.example.invalid", browser_check)
        self.assertNotIn("DEMO_URL", browser_check)
        self.assertNotIn("/lzug/", browser_check)

    def test_favicon_uses_the_publication_base_path_and_existing_product_asset(self) -> None:
        favicon_partial = (ROOT / "docs/publication/blowfish/layouts/_default/baseof.html").read_text()
        config = (ROOT / "docs/publication/hugo.toml").read_text()
        self.assertTrue((ROOT / "brand/derived/favicon.svg").is_file())
        self.assertIn('rel="icon"', favicon_partial)
        self.assertIn('{{ "images/favicon.svg" | relURL }}', favicon_partial)
        self.assertIn("static/images/favicon.svg", config)

    def test_productive_sources_have_a_documentation_owner(self) -> None:
        self.assertFalse((ROOT / "prototypes/publication").exists())
        config = (ROOT / "docs/publication/hugo.toml").read_text()
        for relative in (
            "content/_index.md",
            "content/referenz/_index.md",
            "content/referenz/api/_index.md",
            "content/referenz/datenbank/_index.md",
            "content/quellen/_index.md",
            "hugo.toml",
            "go.mod",
            "public-font.css",
            "blowfish/assets/css/custom.css",
            "blowfish/layouts/index.html",
            "blowfish/layouts/_default/baseof.html",
            "blowfish/layouts/_shortcodes/publication-scope.html",
            "blowfish/static/js/demo-warmup.js",
        ):
            with self.subTest(relative=relative):
                self.assertTrue((ROOT / "docs/publication" / relative).is_file())

        for source, target in (
            ("../../docs/portal/produkt.md", "content/produkt/_index.md"),
            ("../../docs/developers/reference/backend.md", "content/referenz/backend/_index.md"),
            ("../../docs/developers/reference/frontend.md", "content/referenz/frontend/_index.md"),
        ):
            with self.subTest(source=source):
                self.assertIn(f"source = '{source}'", config)
                self.assertIn(f"target = '{target}'", config)

    def test_product_and_portal_adapters_use_one_shared_visual_grammar(self) -> None:
        tokens = (ROOT / "brand/tokens.css").read_text()
        portal_css = (ROOT / "docs/publication/blowfish/assets/css/custom.css").read_text()
        frontend_css = "\n".join(
            (
                (ROOT / "frontend/src/styles.scss").read_text(),
                (ROOT / "frontend/src/app/app.css").read_text(),
                (ROOT / "frontend/src/app/auth/auth-flow.component.css").read_text(),
            )
        )
        for role in (
            "--lzug-role-action-primary",
            "--lzug-role-card-surface",
            "--lzug-role-content-max",
            "--lzug-role-focus",
        ):
            with self.subTest(role=role):
                self.assertIn(role, tokens)
                self.assertIn(role, portal_css)
                self.assertIn(role, frontend_css)
        self.assertNotIn("INTERNAL-", portal_css)

    def test_readme_uses_canonical_publication_boundaries(self) -> None:
        readme = (ROOT / "README.md").read_text()
        for link in (
            "https://lzug.repertoire.papaspyrou.name/",
            "https://github.com/lxndrp/lzug/wiki",
            "CONTRIBUTING.md",
            "docs/developers/index.md",
        ):
            self.assertIn(link, readme)
        for legacy_route in ("/nutzen/", "/betreiben/", "/entwickeln/"):
            self.assertNotIn(f"lzug.repertoire.papaspyrou.name{legacy_route}", readme)

    def test_hugo_owns_routes_and_source_rendering(self) -> None:
        config = (ROOT / "docs/publication/hugo.toml").read_text()
        source_shortcode = (ROOT / "docs/publication/layouts/shortcodes/publication-source.html").read_text()
        self.assertIn("module.mounts", config)
        self.assertIn("outputFormats.quellen", config)
        self.assertIn("readFile", source_shortcode)
        self.assertIn("scripts/export_openapi.py", (ROOT / "Taskfile.yml").read_text())

    def test_generated_public_site_has_one_canonical_linkcheck_entry(self) -> None:
        config = (ROOT / ".lychee.toml").read_text()
        taskfile = (ROOT / "Taskfile.yml").read_text()
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

    def test_pages_deployment_is_manual_fail_closed_and_cannot_enable_pages(self) -> None:
        workflow = workflow_text(".github/workflows/publication.yml")
        triggers = trigger_block(workflow)
        build = job_block(workflow, "build")
        deploy = job_block(workflow, "deploy")
        self.assertIn("BASE_URL: https://lzug.repertoire.papaspyrou.name", workflow)
        self.assertIn("DEMO_URL: ${{ vars.DEMO_URL || 'https://demo.example.invalid' }}", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("actions: read", workflow)
        self.assertIn("python3 -m demo.delivery.contract validate-url", build)
        self.assertIn("--canonical", build)
        self.assertNotIn("GH_TOKEN", workflow)
        self.assertNotIn("github.token", workflow)
        self.assertNotIn("--repository", workflow)
        self.assertIn("pull_request:", triggers)
        self.assertIn("push:", triggers)
        self.assertIn("schedule:", triggers)
        self.assertIn("workflow_dispatch:", triggers)
        self.assertIn('test "$GITHUB_REF" = "refs/heads/master"', build)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", deploy)
        self.assertIn("needs: build", deploy)
        self.assertIn("pages: write", deploy)
        self.assertIn("id-token: write", deploy)
        self.assertIn("environment:\n      name: github-pages", deploy)
        self.assertIn("actions/configure-pages@45bfe0192ca1faeb007ade9deae92b16b8254a0d", deploy)
        self.assertIn("task docs:publication:check DEMO_URL=", build)
        self.assertIn("task docs:publication:linkcheck DEMO_URL=", build)
        self.assertNotIn("--no-sandbox", build)

    def test_browser_checks_run_only_before_manual_publication(self) -> None:
        workflow = workflow_text(".github/workflows/publication.yml")
        build = job_block(workflow, "build")
        self.assertNotIn("paths-filter", workflow)
        self.assertIn("if: github.event_name == 'workflow_dispatch'", build)
        self.assertNotIn("steps.changes", build)


if __name__ == "__main__":
    unittest.main()
