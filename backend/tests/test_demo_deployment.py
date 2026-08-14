from __future__ import annotations

import unittest
from pathlib import Path

from scripts.demo_deployment import (
    ArtifactPair,
    DeploymentError,
    deployment_body,
    readiness_observation,
    validate_demo_status,
    validate_demo_url,
    validate_health,
)


class DemoDeploymentTests(unittest.TestCase):
    pair = ArtifactPair(
        app_image="ghcr.io/lxndrp/lzug-demo-app@sha256:" + "a" * 64,
        seed_image="ghcr.io/lxndrp/lzug-demo-seed@sha256:" + "b" * 64,
        product_tag="v0.1.1",
        product_commit="c" * 40,
        schema_fingerprint="d" * 64,
        seed_revision="e" * 64,
    )

    def resource(self) -> dict:
        return {
            "properties": {
                "configuration": {"activeRevisionsMode": "Single"},
                "provisioningState": "Succeeded",
                "runningStatus": "Running",
                "latestRevisionName": "lzug-demo-app--gh-123-1",
                "latestReadyRevisionName": "lzug-demo-app--gh-123-1",
                "template": {
                    "revisionSuffix": "old",
                    "containers": [
                        {
                            "name": "lzug-demo-app",
                            "image": "ghcr.io/lxndrp/lzug-demo-app@sha256:" + "1" * 64,
                            "volumeMounts": [{"volumeName": "demo-data", "mountPath": "/data"}],
                        }
                    ],
                    "initContainers": [
                        {
                            "name": "lzug-demo-seed",
                            "image": "ghcr.io/lxndrp/lzug-demo-seed@sha256:" + "2" * 64,
                            "volumeMounts": [{"volumeName": "demo-data", "mountPath": "/data"}],
                        }
                    ],
                    "volumes": [{"name": "demo-data", "storageType": "EmptyDir"}],
                    "scale": {"minReplicas": 0, "maxReplicas": 1},
                },
            }
        }

    def test_atomic_revision_update_changes_only_both_images_and_suffix(self) -> None:
        resource = self.resource()
        body, previous = deployment_body(resource, self.pair, "gh-123-1")
        template = body["properties"]["template"]

        self.assertEqual(self.pair.app_image, template["containers"][0]["image"])
        self.assertEqual(self.pair.seed_image, template["initContainers"][0]["image"])
        self.assertEqual("gh-123-1", template["revisionSuffix"])
        self.assertEqual(resource["properties"]["template"]["volumes"], template["volumes"])
        self.assertNotEqual(self.pair.app_image, previous["app_image"])
        self.assertNotEqual(self.pair.seed_image, previous["seed_image"])
        self.assertEqual("old", resource["properties"]["template"]["revisionSuffix"])

    def test_update_rejects_moving_tags_partial_assembly_and_wrong_revision_mode(self) -> None:
        moving = ArtifactPair(
            app_image="ghcr.io/lxndrp/lzug-demo-app:latest",
            seed_image=self.pair.seed_image,
            product_tag=self.pair.product_tag,
            product_commit=self.pair.product_commit,
            schema_fingerprint=self.pair.schema_fingerprint,
            seed_revision=self.pair.seed_revision,
        )
        with self.assertRaisesRegex(DeploymentError, "app_image"):
            deployment_body(self.resource(), moving, "gh-123-1")

        resource = self.resource()
        resource["properties"]["template"]["initContainers"] = []
        with self.assertRaisesRegex(DeploymentError, "exactly one"):
            deployment_body(resource, self.pair, "gh-123-1")

        resource = self.resource()
        resource["properties"]["configuration"]["activeRevisionsMode"] = "Multiple"
        with self.assertRaisesRegex(DeploymentError, "Single revision"):
            deployment_body(resource, self.pair, "gh-123-1")

    def test_readiness_is_distinct_and_requires_the_exact_new_pair(self) -> None:
        resource = self.resource()
        resource["properties"]["template"]["containers"][0]["image"] = self.pair.app_image
        resource["properties"]["template"]["initContainers"][0]["image"] = self.pair.seed_image

        ready, observation = readiness_observation(resource, self.pair, "gh-123-1")
        self.assertTrue(ready)
        self.assertEqual(self.pair.seed_image, observation["seed_image"])

        resource["properties"]["latestReadyRevisionName"] = "lzug-demo-app--old"
        ready, _ = readiness_observation(resource, self.pair, "gh-123-1")
        self.assertFalse(ready)

    def test_health_and_demo_api_bind_the_running_product_schema_and_seed(self) -> None:
        validate_health({"status": "ok", "revision": self.pair.product_commit}, self.pair)
        validate_demo_status(
            {
                "product_version": "0.1.1",
                "product_commit": self.pair.product_commit,
                "schema_fingerprint": self.pair.schema_fingerprint,
                "seed_revision": self.pair.seed_revision,
                "initialized": True,
                "initialization_status": "ready",
                "reset_timezone": "Europe/Berlin",
            },
            self.pair,
        )
        with self.assertRaisesRegex(DeploymentError, "unexpected product commit"):
            validate_health({"status": "ok", "revision": "f" * 40}, self.pair)
        with self.assertRaisesRegex(DeploymentError, "seed_revision"):
            validate_demo_status(
                {
                    "product_version": "0.1.1",
                    "product_commit": self.pair.product_commit,
                    "schema_fingerprint": self.pair.schema_fingerprint,
                    "seed_revision": "f" * 64,
                    "initialized": True,
                    "initialization_status": "ready",
                    "reset_timezone": "Europe/Berlin",
                },
                self.pair,
            )

    def test_demo_url_is_an_https_origin_only(self) -> None:
        self.assertEqual("https://demo.example.org/", validate_demo_url("https://demo.example.org"))
        for invalid in (
            "http://demo.example.org",
            "https://demo.example.org/path",
            "https://user@example.org",
            "https://demo.example.org?token=no",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(DeploymentError):
                validate_demo_url(invalid)

    def test_workflow_has_minimal_oidc_environment_and_failure_contract(self) -> None:
        workflow = Path(".github/workflows/demo-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("push:\n", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("packages: read", workflow)
        self.assertIn("name: demo", workflow)
        self.assertIn("url: ${{ vars.DEMO_URL }}", workflow)
        self.assertIn("azure/login@f5d393ae46f8fde4be8b75f32e3fc50e654ad0ca", workflow)
        self.assertNotIn("secrets.AZURE", workflow)
        self.assertNotIn("AZURE_CREDENTIALS", workflow)
        self.assertEqual(2, workflow.count("gh attestation verify"))
        self.assertIn('for image in "$APP_IMAGE" "$SEED_IMAGE"', workflow)
        self.assertIn("--predicate-type https://cyclonedx.org/bom", workflow)
        self.assertIn("Wait for the new Azure revision to become ready", workflow)
        self.assertIn("Wait separately for application health", workflow)
        self.assertIn("Smoke-test health, API, and the central frontend route", workflow)
        self.assertIn("if: failure()", workflow)
        self.assertIn("previously verified complete pair", workflow)
        publish = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("schema_fingerprint=$(jq -er '.schema_fingerprint'", publish)
        self.assertIn("steps.images.outputs.schema_fingerprint", publish)
        pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        full_quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        pull_request_infra = pull_request.split("\n  infra:\n", 1)[1].split("\n  e2e:\n", 1)[0]
        full_quality_infra = full_quality.split("\n  infra:\n", 1)[1].split(
            "\n  container:\n", 1
        )[0]
        for workflow_infra in (pull_request_infra, full_quality_infra):
            self.assertIn("actions/setup-python@", workflow_infra)
            self.assertIn("astral-sh/setup-uv@", workflow_infra)
            self.assertIn("task quality:infra quality:demo-deployment", workflow_infra)
        self.assertIn("quality:demo-deployment:", taskfile)


if __name__ == "__main__":
    unittest.main()
