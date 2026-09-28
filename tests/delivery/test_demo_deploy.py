from __future__ import annotations

import unittest

from tests.delivery.workflow_contract import job_block, workflow_text


class DemoDeployWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = workflow_text(".github/workflows/demo-deploy.yml")
        cls.release = workflow_text(".github/workflows/release.yml")
        cls.snapshot = workflow_text(".github/workflows/snapshot.yml")
        cls.script = workflow_text("scripts/demo-deploy.ps1")

    def test_deployment_receives_only_the_immutable_image_pair(self) -> None:
        deploy = job_block(self.release, "demo-deploy") + job_block(self.snapshot, "demo-deploy")
        self.assertIn("app_image: ${{ needs.demo-publish.outputs.app_image }}", deploy)
        self.assertIn("seed_image: ${{ needs.demo-publish.outputs.seed_image }}", deploy)
        for field in (
            "product_tag",
            "product_commit",
            "runtime_contract",
            "schema_fingerprint",
            "seed_revision",
        ):
            with self.subTest(field=field):
                self.assertNotIn(f"{field}:", deploy)
                self.assertNotIn(f"{field}:", self.workflow)
                self.assertNotIn(field.upper(), self.script)

    def test_release_candidates_do_not_promote_the_stable_demo(self) -> None:
        release_deploy = job_block(self.release, "demo-deploy")
        self.assertIn("!contains(needs.preflight.outputs.release_tag, '-')", release_deploy)

    def test_source_and_provenance_gates_remain_before_azure_login(self) -> None:
        validation = self.workflow.index("name: Validate immutable platform inputs")
        provenance = self.workflow.index(
            "name: Verify provenance attestations for both selected digests"
        )
        azure_login = self.workflow.index("name: Log in to Azure using GitHub OIDC")
        self.assertLess(validation, provenance)
        self.assertLess(provenance, azure_login)
        self.assertIn('stable:deploy) test "$GITHUB_REF" = refs/heads/master ;;', self.workflow)
        self.assertIn("snapshot:deploy)", self.workflow)
        self.assertIn("refs/tags/snapshot/v", self.workflow)
        self.assertIn(':rollback) test "$GITHUB_REF" = refs/heads/master', self.workflow)

    def test_deployment_acceptance_waits_for_azure_revision_and_runtime_readiness(self) -> None:
        self.assertIn("runningState | [0]", self.script)
        self.assertIn("$state -eq 'Running'", self.script)
        self.assertIn("/api/ready", self.script)
        self.assertNotIn("/api/demo/status", self.script)
        self.assertNotIn("/api/openapi.json", self.script)
        self.assertNotIn('$($env:DEMO_URL)/"', self.script)


if __name__ == "__main__":
    unittest.main()
