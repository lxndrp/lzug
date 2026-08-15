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

    def test_complete_quality_includes_demo_pair(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")

        self.assertIn("quality:demo:", taskfile)
        self.assertIn("scripts/demo-container-smoke.sh", taskfile)
        self.assertIn('snapshot|demo/v0.2.0-SNAPSHOT.$short_revision', taskfile)
        self.assertIn("quality:demo", pull_request)
        self.assertIn("quality:demo", quality)

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
        self.assertIn("validate-quality", workflow)
        self.assertIn("validate-milestone", workflow)
        self.assertIn("validate-releases", workflow)
        self.assertIn("Verify automatic demo Environment tag policy", workflow)
        self.assertIn('.type == "branch" and .name == "master"', workflow)
        self.assertIn('.type == "tag" and .name == "demo/*-SNAPSHOT.*"', workflow)
        self.assertIn('.type != "required_reviewers"', workflow)
        self.assertNotIn("git tag ", workflow)
        self.assertNotIn("git push ", workflow)
        self.assertNotIn("environment: release", workflow)
        self.assertNotIn(":latest", workflow)

        build = workflow.index("- name: Build the snapshot seed candidate exactly once")
        reject = workflow.index("- name: Reject occupied snapshot OCI references")
        attest = workflow.index("- name: Attest snapshot application provenance")
        deploy = workflow.index("  deploy:\n")
        smoke = workflow.index("- name: Smoke-test health, readiness, demo API")
        self.assertLess(build, reject)
        self.assertLess(reject, attest)
        self.assertIn("Could not verify snapshot reference availability", workflow[reject:attest])
        self.assertLess(attest, deploy)
        self.assertLess(deploy, smoke)
        self.assertEqual(4, workflow.count("uses: actions/attest@"))
        self.assertIn("name: demo", workflow[deploy:])
        self.assertIn("id-token: write", workflow[deploy:])
        self.assertIn("azure/login@f5d393ae46f8fde4be8b75f32e3fc50e654ad0ca", workflow)
        self.assertIn("needs.publish.outputs.app_image", workflow[deploy:])
        self.assertIn("needs.publish.outputs.seed_image", workflow[deploy:])
        self.assertIn("--signer-workflow lxndrp/lzug/.github/workflows/demo-snapshot.yml", workflow)

        release_publish = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", release_publish)
        self.assertIn("environment: release", release_publish)
        self.assertIn("select(.isDraft == false)", release_publish)


if __name__ == "__main__":
    unittest.main()
