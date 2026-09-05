from __future__ import annotations

import unittest
from pathlib import Path

from tests.delivery.workflow_contract import job_block, mapping_block, workflow_text


class DemoDeliveryContractTests(unittest.TestCase):
    product_tag = "v0.1.1"
    product_commit = "948cab736131894950dbad57533e80f7238dd545"

    def test_product_image_excludes_demo_provider_and_demo_images_are_separate(self) -> None:
        product = Path("Dockerfile").read_text(encoding="utf-8")
        demo_app = Path("demo/Dockerfile.demo").read_text(encoding="utf-8")
        demo_seed = Path("demo/Dockerfile.demo-seed").read_text(encoding="utf-8")

        self.assertNotIn("demo/app.py", product)
        self.assertNotIn("frontend/demo-overlays", product)
        self.assertIn("demo/app.py", demo_app)
        self.assertEqual(2, demo_app.count("demo/contract.py"))
        self.assertIn("demo/contract.py", demo_seed)
        self.assertIn("frontend/demo-overlays", demo_app)
        self.assertIn("LZUG_FRONTEND_CONFIGURATION=demo", demo_app)
        self.assertIn("demo.artifacts build-seed", demo_seed)
        self.assertIn("SEED_REVISION", demo_app)
        self.assertNotIn("VOLUME", demo_app)
        self.assertNotIn("VOLUME", demo_seed)
        for name, runtime_dockerfile in (("product", product), ("demo", demo_app)):
            with self.subTest(runtime=name):
                self.assertIn("backend/application.py", runtime_dockerfile)
                self.assertIn("backend/fastapi_app.py", runtime_dockerfile)

    def test_stable_release_calls_reusable_promotion_after_publication(self) -> None:
        release = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
        promotion = Path(".github/workflows/demo-promote.yml").read_text(encoding="utf-8")

        self.assertIn('gh release edit "$RELEASE_TAG" --repo "$GH_REPO" --draft=false', release)
        self.assertIn("uses: ./.github/workflows/demo-promote.yml", release)
        self.assertIn("needs: [preflight, publish]", release)
        self.assertIn("!contains(needs.preflight.outputs.release_tag, '-rc.')", release)
        self.assertIn("workflow_call:", promotion)
        self.assertNotIn("release:\n", promotion)
        self.assertNotIn("workflow_dispatch:", promotion)
        self.assertIn("uses: ./.github/workflows/demo-publish.yml", promotion)
        self.assertIn("uses: ./.github/workflows/demo-deploy.yml", promotion)
        self.assertIn("needs: publish", promotion)

    def test_stable_promotion_passes_actions_read_through_nested_deployment(self) -> None:
        workflows_and_jobs = (
            (workflow_text(".github/workflows/release.yml"), "promote-demo"),
            (workflow_text(".github/workflows/demo-promote.yml"), "deploy"),
            (workflow_text(".github/workflows/demo-deploy.yml"), "deploy"),
        )

        for workflow, job_id in workflows_and_jobs:
            with self.subTest(job=job_id, workflow=workflow):
                permissions = mapping_block(job_block(workflow, job_id), "permissions", indent=4)
                self.assertIn("actions: read", permissions)

    def test_publish_resolves_one_attested_immutable_pair_from_the_product_tag(self) -> None:
        workflow = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_call:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertNotIn("environment: release", workflow)
        self.assertIn("select(.isDraft == false)", workflow)
        self.assertIn("branch=master&head_sha=$target_sha&status=success", workflow)
        self.assertIn('.head_branch == "master"', workflow)
        self.assertIn("ghcr.io/${GH_REPO,,}-demo-app", workflow)
        self.assertIn("ghcr.io/${GH_REPO,,}-demo-seed", workflow)
        self.assertIn("absent:absent", workflow)
        self.assertIn("present:present", workflow)
        self.assertIn("partially published and will not be overwritten", workflow)
        self.assertIn("steps.availability.outputs.reuse != 'true'", workflow)
        self.assertEqual(4, workflow.count("uses: actions/attest@"))
        self.assertNotIn(":latest", workflow)
        self.assertNotIn(":demo", workflow)

        preflight = job_block(workflow, "preflight")
        publish = job_block(workflow, "publish")
        resolution = job_block(workflow, "resolve")
        self.assertIn("python3 -m demo.contract identity", preflight)
        self.assertIn("--channel stable", preflight)
        self.assertIn("python3 -m demo.contract manifest-field", publish)
        self.assertIn("python3 -m demo.contract validate-pair", publish)
        self.assertIn("python3 -m demo.contract manifest-field", resolution)
        self.assertIn("python3 -m demo.contract validate-pair", resolution)
        self.assertIn("scripts/verify-demo-image-pair.sh", resolution)
        self.assertNotIn(".product.tag ==", workflow)
        self.assertNotIn('test("^[0-9a-f]{64}$")', workflow)
        self.assertEqual(1, resolution.count("--predicate-type https://slsa.dev/provenance/v1"))
        self.assertNotIn("https://cyclonedx.org/bom", resolution)

    def test_publish_builds_inspects_and_pushes_the_same_seed_image(self) -> None:
        workflow = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        dockerfile = Path("demo/Dockerfile.demo-seed").read_text(encoding="utf-8")

        self.assertIn("load: true", workflow)
        self.assertIn('docker create "$SEED_CANDIDATE"', workflow)
        self.assertIn('--expected-product-tag "$PRODUCT_TAG"', workflow)
        self.assertIn('--expected-product-commit "$TARGET_SHA"', workflow)
        self.assertIn('--expected-schema-fingerprint "$expected_schema_fingerprint"', workflow)
        self.assertIn('docker tag "$SEED_CANDIDATE" "$SEED_REF"', workflow)
        self.assertIn('docker push "$SEED_REF"', workflow)
        self.assertIn('docker buildx imagetools inspect "$SEED_REF"', workflow)
        self.assertIn("SEED_REVISION=${{ steps.images.outputs.seed_revision }}", workflow)
        self.assertNotIn("demo.artifacts build-seed", workflow)
        self.assertEqual(1, dockerfile.count("demo.artifacts build-seed"))

    def test_publish_reads_manifest_fields_through_the_shared_contract(self) -> None:
        workflow = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")

        self.assertIn("--kind seed", workflow)
        self.assertIn("--kind app", workflow)
        self.assertIn("--field schema_fingerprint", workflow)
        self.assertIn('--expected-product-tag "$PRODUCT_TAG"', workflow)
        self.assertIn('--expected-product-commit "$TARGET_SHA"', workflow)
        self.assertNotIn("schema_fingerprint=$(jq", workflow)

    def test_deployment_is_reusable_and_preserves_security_boundaries(self) -> None:
        workflow = Path(".github/workflows/demo-deploy.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_call:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("push:\n", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("name: demo", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: read", workflow)
        self.assertIn("python3 -m demo.contract validate-deployment", workflow)
        self.assertIn("python3 -m demo.contract signer-workflow", workflow)
        self.assertIn("scripts/verify-demo-image-pair.sh", workflow)
        self.assertIn("azure/login@7ddb5af1ef8758cf1353cf3b42f940aee27ba21c", workflow)
        self.assertIn("scripts/demo_deployment.py deploy", workflow)
        self.assertIn("wait-readiness", workflow)
        self.assertIn("wait-application-readiness", workflow)
        self.assertIn("demo_deployment.py smoke", workflow)
        self.assertNotIn("wait-health", workflow)
        self.assertEqual(1, workflow.count("gh attestation verify"))
        self.assertIn("--predicate-type https://slsa.dev/provenance/v1", workflow)
        self.assertNotIn("--predicate-type https://cyclonedx.org/bom", workflow)
        self.assertIn("promotion_channel:", workflow)
        self.assertIn('--promotion-channel "${{ inputs.promotion_channel }}"', workflow)
        self.assertIn('--operation "${{ inputs.operation }}"', workflow)
        self.assertIn('--github-ref "$GITHUB_REF"', workflow)
        self.assertLess(
            workflow.index("scripts/verify-demo-image-pair.sh"),
            workflow.index("azure/login@"),
        )

    def test_snapshot_reuses_quality_evidence_and_deployment_workflow(self) -> None:
        workflow = Path(".github/workflows/demo-snapshot.yml").read_text(encoding="utf-8")

        self.assertIn("push:\n    tags:", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertIn("EVENT_CREATED", workflow)
        self.assertIn('test "$EVENT_BEFORE" = "$zero_sha"', workflow)
        self.assertIn("refs/remotes/origin/master", workflow)
        self.assertIn("actions/workflows/quality.yml/runs?branch=master", workflow)
        self.assertIn(".head_sha == $sha", workflow)
        self.assertIn('.head_branch == "master"', workflow)
        self.assertNotIn("uses: ./.github/workflows/quality.yml", workflow)
        self.assertNotIn("/milestones", workflow)
        self.assertNotIn("/releases", workflow)
        self.assertNotIn("/environments/demo", workflow)
        self.assertNotIn("deployment-branch-policies", workflow)
        self.assertNotIn("environment: release", workflow)
        self.assertIn("needs: preflight", workflow)
        self.assertIn("uses: ./.github/workflows/demo-deploy.yml", workflow)
        self.assertIn("app_image: ${{ needs.publish.outputs.app_image }}", workflow)
        self.assertIn("SEED_REVISION=${{ steps.pair.outputs.seed_revision }}", workflow)
        self.assertIn("python3 -m demo.contract identity", workflow)
        self.assertIn("python3 -m demo.contract manifest-field", workflow)
        self.assertIn("python3 -m demo.contract validate-pair", workflow)
        self.assertEqual(4, workflow.count("uses: actions/attest@"))
        self.assertNotIn("azure/login@", workflow)

    def test_pre_azure_pair_verifier_reads_both_digest_bound_manifests(self) -> None:
        verifier = Path("scripts/verify-demo-image-pair.sh").read_text(encoding="utf-8")

        self.assertIn('docker pull "$app_image"', verifier)
        self.assertIn('docker pull "$seed_image"', verifier)
        self.assertIn("/app/demo-app-manifest.json", verifier)
        self.assertIn("/opt/lzug-demo/seed/manifest.json", verifier)
        self.assertIn("python3 -m demo.contract verify-pair-manifests", verifier)
        self.assertIn("verify-pair-manifests", verifier)
        self.assertIn('--expected-seed-revision "$seed_revision"', verifier)

    def test_complete_quality_includes_demo_pair(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")

        self.assertIn("quality:demo:", taskfile)
        self.assertIn("quality:demo-matrix:", taskfile)
        self.assertIn("- quality:demo-matrix", taskfile)
        self.assertIn("scripts/demo-container-smoke.sh", taskfile)
        self.assertIn("SEED_REVISION=$seed_revision", taskfile)
        self.assertIn("quality:demo", pull_request)
        self.assertIn("quality:demo", quality)

    def test_environment_policies_prepare_stable_and_snapshot_tags(self) -> None:
        main = Path("infra/demo/main.tf").read_text(encoding="utf-8")
        variables = Path("infra/demo/variables.tf").read_text(encoding="utf-8")

        self.assertIn('pattern = "demo/v*-SNAPSHOT.*"', main)
        self.assertIn('pattern = "v*"', main)
        self.assertIn("for_each = var.github_environment_deployment_policy_ids", main)
        self.assertIn("length(var.github_environment_deployment_policy_ids) == 0", variables)


if __name__ == "__main__":
    unittest.main()
