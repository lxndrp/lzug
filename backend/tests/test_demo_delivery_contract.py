from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from demo.artifacts import build_seed


class DemoDeliveryContractTests(unittest.TestCase):
    product_tag = "v0.1.1"
    product_commit = "948cab736131894950dbad57533e80f7238dd545"

    def test_product_image_excludes_demo_provider_and_demo_images_are_separate(self) -> None:
        product = Path("Dockerfile").read_text(encoding="utf-8")
        demo_app = Path("Dockerfile.demo").read_text(encoding="utf-8")
        demo_seed = Path("Dockerfile.demo-seed").read_text(encoding="utf-8")

        self.assertNotIn("demo/app.py", product)
        self.assertNotIn("frontend/demo-overlays", product)
        self.assertIn("demo/app.py", demo_app)
        self.assertIn("frontend/demo-overlays", demo_app)
        self.assertIn("LZUG_FRONTEND_CONFIGURATION=demo", demo_app)
        self.assertIn("demo.artifacts build-seed", demo_seed)
        self.assertNotIn("VOLUME", demo_app)
        self.assertNotIn("VOLUME", demo_seed)

    def test_publish_contract_uses_two_attested_immutable_packages(self) -> None:
        workflow = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("environment: release", workflow)
        self.assertIn("select(.isDraft == false)", workflow)
        self.assertIn("ghcr.io/${GH_REPO,,}-demo-app", workflow)
        self.assertIn("ghcr.io/${GH_REPO,,}-demo-seed", workflow)
        self.assertIn("Immutable demo reference already exists", workflow)
        self.assertEqual(4, workflow.count("uses: actions/attest@"))
        self.assertNotIn(":latest", workflow)
        self.assertNotIn(":demo", workflow)

    def test_publish_builds_inspects_and_pushes_the_same_seed_image(self) -> None:
        workflow = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        dockerfile = Path("Dockerfile.demo-seed").read_text(encoding="utf-8")

        build = workflow.index("- name: Build the demo seed candidate exactly once")
        inspect = workflow.index(
            "- name: Inspect the embedded seed and derive immutable references"
        )
        reject = workflow.index("- name: Reject moving or replacing an existing demo reference")
        push = workflow.index("- name: Tag and publish the inspected demo seed")
        attest = workflow.index("- name: Attest demo application provenance")

        self.assertLess(build, inspect)
        self.assertLess(inspect, reject)
        self.assertLess(reject, push)
        self.assertLess(push, attest)
        self.assertIn("load: true", workflow[build:inspect])
        self.assertIn('docker create "$SEED_CANDIDATE"', workflow[inspect:reject])
        self.assertIn('--expected-product-tag "$PRODUCT_TAG"', workflow[inspect:reject])
        self.assertIn('--expected-product-commit "$TARGET_SHA"', workflow[inspect:reject])
        self.assertIn(
            '--expected-schema-fingerprint "$expected_schema_fingerprint"',
            workflow[inspect:reject],
        )
        self.assertIn('docker tag "$SEED_CANDIDATE" "$SEED_REF"', workflow[push:attest])
        self.assertIn('docker push "$SEED_REF"', workflow[push:attest])
        self.assertIn('docker buildx imagetools inspect "$SEED_REF"', workflow[push:attest])
        self.assertIn("^sha256:[0-9a-f]{64}$", workflow[push:attest])
        self.assertNotIn("demo.artifacts build-seed", workflow)
        self.assertEqual(1, dockerfile.count("demo.artifacts build-seed"))

    def test_publish_reads_schema_fingerprint_from_canonical_seed_manifest(self) -> None:
        workflow = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        selector_match = re.search(
            r"schema_fingerprint=\$\(jq -er '([^']+)' " r'"\$temporary_directory/manifest\.json"\)',
            workflow,
        )
        self.assertIsNotNone(selector_match)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            manifest = build_seed(
                Path("."),
                root / "lzug.sqlite",
                manifest_path,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            selected_fingerprint = subprocess.run(
                ["jq", "-er", selector_match.group(1), manifest_path],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        self.assertEqual(manifest["schema"]["fingerprint"], selected_fingerprint)

    def test_pre_azure_pair_verifier_reads_both_digest_bound_manifests(self) -> None:
        verifier = Path("scripts/verify-demo-image-pair.sh").read_text(encoding="utf-8")

        self.assertIn('docker pull "$app_image"', verifier)
        self.assertIn('docker pull "$seed_image"', verifier)
        self.assertIn("/app/demo-app-manifest.json", verifier)
        self.assertIn("/opt/lzug-demo/seed/manifest.json", verifier)
        self.assertIn("verify-pair-manifests", verifier)
        self.assertIn('--expected-runtime-contract "$runtime_contract"', verifier)

    def test_complete_quality_includes_demo_pair(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")

        self.assertIn("quality:demo:", taskfile)
        self.assertIn("scripts/demo-container-smoke.sh", taskfile)
        self.assertIn("snapshot|demo/v0.2.0-SNAPSHOT.$short_revision", taskfile)
        self.assertIn("quality:demo", pull_request)
        self.assertIn("quality:demo", quality)

    def test_environment_policy_adoption_is_atomic_and_optional(self) -> None:
        main = Path("infra/demo/main.tf").read_text(encoding="utf-8")
        variables = Path("infra/demo/variables.tf").read_text(encoding="utf-8")
        example = Path("infra/demo/terraform.tfvars.example").read_text(encoding="utf-8")

        self.assertIn('pattern = "demo/v*-SNAPSHOT.*"', main)
        self.assertIn("for_each = var.github_environment_deployment_policy_ids", main)
        self.assertIn("to = github_repository_environment_deployment_policy.demo[each.key]", main)
        self.assertIn('id = "${var.github_repository}:demo:${each.value}"', main)
        self.assertIn('toset(["master", "snapshot"])', variables)
        self.assertIn("length(var.github_environment_deployment_policy_ids) == 0", variables)
        self.assertIn("github_environment_deployment_policy_ids = {}", example)

    def test_snapshot_promotion_is_one_tag_driven_publish_and_deploy_run(self) -> None:
        workflow = Path(".github/workflows/demo-snapshot.yml").read_text(encoding="utf-8")

        self.assertIn("push:\n    tags:", workflow)
        self.assertIn('"demo/v[0-9]*.[0-9]*.[0-9]*-SNAPSHOT.', workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("branches:", workflow)
        self.assertIn("EVENT_CREATED", workflow)
        self.assertIn('test "$EVENT_BEFORE" = "$zero_sha"', workflow)
        self.assertIn('git cat-file -t "$SNAPSHOT_TAG"', workflow)
        self.assertIn("Snapshot tags must be new and must never be moved", workflow)
        self.assertIn("Could not verify target product-tag availability", workflow)
        self.assertIn("refs/remotes/origin/master", workflow)
        self.assertIn("validate-milestone", workflow)
        self.assertIn("validate-releases", workflow)
        self.assertIn("Verify demo Environment activation policy before Azure mutation", workflow)
        self.assertIn('.type == "branch" and .name == "master"', workflow)
        self.assertIn('.type == "tag" and .name == "demo/v*-SNAPSHOT.*"', workflow)
        self.assertIn('.type != "required_reviewers"', workflow)
        self.assertNotIn("git tag ", workflow)
        self.assertNotIn("git push ", workflow)
        self.assertNotIn("environment: release", workflow)
        self.assertNotIn(":latest", workflow)
        self.assertNotIn("actions/workflows/quality.yml/runs", workflow)
        self.assertNotIn("validate-quality", workflow)

        quality_job = workflow.index("  quality:\n")
        publish = workflow.index("  publish:\n")
        deploy = workflow.index("  deploy:\n")
        self.assertIn("actions: read", workflow[deploy:])
        self.assertLess(quality_job, publish)
        self.assertLess(publish, deploy)

        preflight_contract = workflow[:quality_job]
        self.assertNotIn("Environment activation policy", preflight_contract)
        self.assertNotIn("deployment-branch-policies", preflight_contract)

        quality_contract = workflow[quality_job:publish]
        self.assertIn("needs: preflight", quality_contract)
        self.assertIn("uses: ./.github/workflows/quality.yml", quality_contract)
        self.assertIn(
            "revision: ${{ needs.preflight.outputs.target_sha }}",
            quality_contract,
        )

        publish_contract = workflow[publish:deploy]
        self.assertIn("needs: [preflight, quality]", publish_contract)
        self.assertNotIn("if: always()", publish_contract)

        deploy_contract = workflow[deploy:]
        self.assertIn("      - publish", deploy_contract)
        self.assertNotIn("if: always()", deploy_contract)

        build = workflow.index("- name: Build the snapshot seed candidate exactly once")
        reject = workflow.index("- name: Reject occupied snapshot OCI references")
        attest = workflow.index("- name: Attest snapshot application provenance")
        smoke = workflow.index("- name: Smoke-test health, readiness, demo API")
        self.assertLess(build, reject)
        self.assertLess(reject, attest)
        self.assertIn("Could not verify snapshot reference availability", workflow[reject:attest])
        self.assertLess(attest, deploy)
        self.assertLess(deploy, smoke)
        self.assertEqual(4, workflow.count("uses: actions/attest@"))
        self.assertIn("name: demo", workflow[deploy:])
        self.assertIn(
            "Validate the effective DEMO_URL before Azure mutation",
            workflow[deploy:],
        )
        self.assertIn("scripts/validate_demo_url_contract.py validate", workflow[deploy:])
        self.assertIn("id-token: write", workflow[deploy:])
        self.assertIn("azure/login@f5d393ae46f8fde4be8b75f32e3fc50e654ad0ca", workflow)
        self.assertIn("needs.publish.outputs.app_image", workflow[deploy:])
        self.assertIn("needs.publish.outputs.seed_image", workflow[deploy:])
        self.assertIn("needs.publish.outputs.runtime_contract", workflow[deploy:])
        self.assertIn("scripts/verify-demo-image-pair.sh", workflow[deploy:])
        manifest_verification = workflow.index(
            "Verify digest-bound pair manifests before Azure mutation",
            deploy,
        )
        policy_verification = workflow.index(
            "Verify demo Environment activation policy before Azure mutation",
            deploy,
        )
        azure_login = workflow.index("Log in to Azure using GitHub OIDC", deploy)
        self.assertLess(
            manifest_verification,
            policy_verification,
        )
        self.assertLess(policy_verification, azure_login)
        self.assertLess(
            workflow.index("Validate the effective DEMO_URL before Azure mutation", deploy),
            azure_login,
        )
        self.assertIn("--signer-workflow lxndrp/lzug/.github/workflows/demo-snapshot.yml", workflow)

        release_publish = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", release_publish)
        self.assertIn("environment: release", release_publish)
        self.assertIn("select(.isDraft == false)", release_publish)


if __name__ == "__main__":
    unittest.main()
