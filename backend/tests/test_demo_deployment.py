from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from email.message import Message
from http import HTTPStatus
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch
from urllib.error import HTTPError

from scripts.demo_deployment import (
    ArtifactPair,
    AzureTarget,
    DeploymentError,
    _http_get,
    deploy,
    deployment_body,
    readiness_observation,
    smoke,
    validate_application_readiness,
    validate_authentication_required,
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
        runtime_contract="lzug-demo-health-ready-v1",
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
                            "env": [
                                {"name": "LZUG_DATA_DIR", "value": "/data"},
                                {
                                    "name": "LZUG_DEPLOYMENT_DIGEST",
                                    "value": "sha256:" + "1" * 64,
                                },
                            ],
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

    @staticmethod
    def http_response(status: HTTPStatus, body: object, content_type: str) -> MagicMock:
        response = MagicMock()
        response.getcode.return_value = status
        response.headers.get_content_type.return_value = content_type
        response.read.return_value = (
            json.dumps(body).encode("utf-8")
            if content_type == "application/json"
            else str(body).encode()
        )
        return response

    @staticmethod
    def http_error(status: HTTPStatus, body: object) -> HTTPError:
        headers = Message()
        headers["Content-Type"] = "application/json"
        return HTTPError(
            "https://demo.example.org/api/openapi.json",
            status,
            status.phrase,
            headers,
            BytesIO(json.dumps(body).encode("utf-8")),
        )

    def test_atomic_revision_update_changes_only_both_images_and_suffix(self) -> None:
        resource = self.resource()
        body, previous = deployment_body(resource, self.pair, "gh-123-1")
        template = body["properties"]["template"]

        self.assertEqual(self.pair.app_image, template["containers"][0]["image"])
        self.assertEqual(self.pair.seed_image, template["initContainers"][0]["image"])
        self.assertEqual(
            "sha256:" + "a" * 64,
            template["containers"][0]["env"][1]["value"],
        )
        self.assertEqual("gh-123-1", template["revisionSuffix"])
        self.assertEqual(resource["properties"]["template"]["volumes"], template["volumes"])
        self.assertNotEqual(self.pair.app_image, previous["app_image"])
        self.assertNotEqual(self.pair.seed_image, previous["seed_image"])
        self.assertEqual("old", resource["properties"]["template"]["revisionSuffix"])

    def test_deploy_accepts_successful_patch_without_response_body(self) -> None:
        responses = (
            subprocess.CompletedProcess([], 0, json.dumps(self.resource()), ""),
            subprocess.CompletedProcess([], 0, "", ""),
        )
        target = AzureTarget(
            "11111111-1111-1111-1111-111111111111",
            "lzug-demo-rg",
            "lzug-demo-app",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / "deployment.json"
            with patch("scripts.demo_deployment.subprocess.run", side_effect=responses) as run:
                deploy(target, self.pair, "gh-123-1", record)

            evidence = json.loads(record.read_text(encoding="utf-8"))

        self.assertEqual(self.pair.app_image, evidence["target"]["app_image"])
        self.assertEqual("gh-123-1", evidence["revision_suffix"])
        patch_command = run.call_args_list[1].args[0]
        self.assertEqual("patch", patch_command[patch_command.index("--method") + 1])
        self.assertEqual("none", patch_command[patch_command.index("--output") + 1])

    def test_deploy_still_requires_json_from_the_initial_read(self) -> None:
        response = subprocess.CompletedProcess([], 0, "", "")
        target = AzureTarget(
            "11111111-1111-1111-1111-111111111111",
            "lzug-demo-rg",
            "lzug-demo-app",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / "deployment.json"
            with (
                patch("scripts.demo_deployment.subprocess.run", return_value=response),
                self.assertRaisesRegex(DeploymentError, "returned invalid JSON"),
            ):
                deploy(target, self.pair, "gh-123-1", record)

            self.assertFalse(record.exists())

    def test_deploy_fails_closed_when_the_patch_is_rejected(self) -> None:
        responses = (
            subprocess.CompletedProcess([], 0, json.dumps(self.resource()), ""),
            subprocess.CompletedProcess([], 1, "", "Azure rejected the update"),
        )
        target = AzureTarget(
            "11111111-1111-1111-1111-111111111111",
            "lzug-demo-rg",
            "lzug-demo-app",
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            record = Path(temporary_directory) / "deployment.json"
            with (
                patch("scripts.demo_deployment.subprocess.run", side_effect=responses),
                self.assertRaisesRegex(DeploymentError, "Azure rejected the update"),
            ):
                deploy(target, self.pair, "gh-123-1", record)

            self.assertFalse(record.exists())

    def test_update_rejects_moving_tags_partial_assembly_and_wrong_revision_mode(self) -> None:
        moving = ArtifactPair(
            app_image="ghcr.io/lxndrp/lzug-demo-app:latest",
            seed_image=self.pair.seed_image,
            product_tag=self.pair.product_tag,
            product_commit=self.pair.product_commit,
            runtime_contract=self.pair.runtime_contract,
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
        validate_application_readiness(
            {"status": "ready", "revision": self.pair.product_commit}, self.pair
        )
        validate_demo_status(
            {
                "product_version": "0.1.1",
                "product_commit": self.pair.product_commit,
                "runtime_contract": self.pair.runtime_contract,
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
        with self.assertRaisesRegex(DeploymentError, "status=ready"):
            validate_application_readiness(
                {"status": "unavailable", "revision": self.pair.product_commit}, self.pair
            )
        with self.assertRaisesRegex(DeploymentError, "seed_revision"):
            validate_demo_status(
                {
                    "product_version": "0.1.1",
                    "product_commit": self.pair.product_commit,
                    "runtime_contract": self.pair.runtime_contract,
                    "schema_fingerprint": self.pair.schema_fingerprint,
                    "seed_revision": "f" * 64,
                    "initialized": True,
                    "initialization_status": "ready",
                    "reset_timezone": "Europe/Berlin",
                },
                self.pair,
            )

    def test_snapshot_pair_uses_visible_non_release_identity_in_demo_status(self) -> None:
        revision = "abcdef0123456789abcdef0123456789abcdef01"
        pair = ArtifactPair(
            app_image=self.pair.app_image,
            seed_image=self.pair.seed_image,
            product_tag="demo/v0.2.0-SNAPSHOT.abcdef0",
            product_commit=revision,
            runtime_contract=self.pair.runtime_contract,
            schema_fingerprint=self.pair.schema_fingerprint,
            seed_revision=self.pair.seed_revision,
        )
        pair.validate()
        validate_demo_status(
            {
                "product_version": "v0.2.0-SNAPSHOT@abcdef0",
                "product_commit": revision,
                "runtime_contract": pair.runtime_contract,
                "schema_fingerprint": pair.schema_fingerprint,
                "seed_revision": pair.seed_revision,
                "initialized": True,
                "initialization_status": "ready",
                "reset_timezone": "Europe/Berlin",
            },
            pair,
        )

    def test_protected_openapi_accepts_only_401_with_structured_auth_body(self) -> None:
        authentication_error = {"error": "Authentication required."}
        with patch(
            "scripts.demo_deployment.urlopen",
            side_effect=self.http_error(HTTPStatus.UNAUTHORIZED, authentication_error),
        ):
            payload, content_type = _http_get(
                "https://demo.example.org/api/openapi.json",
                expect_json=True,
                expected_status=HTTPStatus.UNAUTHORIZED,
            )

        validate_authentication_required(payload, content_type)

    def test_protected_openapi_rejects_anonymous_200_and_other_statuses(self) -> None:
        authentication_error = {"error": "Authentication required."}
        responses = (
            self.http_response(HTTPStatus.OK, authentication_error, "application/json"),
            self.http_error(HTTPStatus.FORBIDDEN, authentication_error),
        )
        for response, actual_status in zip(
            responses, (HTTPStatus.OK, HTTPStatus.FORBIDDEN), strict=True
        ):
            with (
                self.subTest(status=actual_status),
                patch("scripts.demo_deployment.urlopen", side_effect=[response]),
                self.assertRaisesRegex(
                    DeploymentError,
                    f"returned HTTP {actual_status}; expected HTTP 401",
                ),
            ):
                _http_get(
                    "https://demo.example.org/api/openapi.json",
                    expect_json=True,
                    expected_status=HTTPStatus.UNAUTHORIZED,
                )

    def test_protected_openapi_rejects_unexpected_auth_body(self) -> None:
        for payload, content_type in (
            ({"error": "Forbidden."}, "application/json"),
            ({"error": "Authentication required.", "detail": "extra"}, "application/json"),
            ({"error": "Authentication required."}, "text/plain"),
        ):
            with (
                self.subTest(payload=payload, content_type=content_type),
                self.assertRaises(DeploymentError),
            ):
                validate_authentication_required(payload, content_type)

    def test_smoke_keeps_health_demo_status_and_frontend_checks(self) -> None:
        responses = (
            ({"status": "ok", "revision": self.pair.product_commit}, "application/json"),
            ({"status": "ready", "revision": self.pair.product_commit}, "application/json"),
            (
                {
                    "product_version": "0.1.1",
                    "product_commit": self.pair.product_commit,
                    "runtime_contract": self.pair.runtime_contract,
                    "schema_fingerprint": self.pair.schema_fingerprint,
                    "seed_revision": self.pair.seed_revision,
                    "initialized": True,
                    "initialization_status": "ready",
                    "reset_timezone": "Europe/Berlin",
                },
                "application/json",
            ),
            ({"error": "Authentication required."}, "application/json"),
            ("<app-root></app-root>", "text/html"),
        )
        with patch("scripts.demo_deployment._http_get", side_effect=responses) as http_get:
            smoke("https://demo.example.org", self.pair)

        self.assertEqual(
            [
                call("https://demo.example.org/api/health", expect_json=True),
                call("https://demo.example.org/api/ready", expect_json=True),
                call("https://demo.example.org/api/demo/status", expect_json=True),
                call(
                    "https://demo.example.org/api/openapi.json",
                    expect_json=True,
                    expected_status=HTTPStatus.UNAUTHORIZED,
                ),
                call("https://demo.example.org/", expect_json=False),
            ],
            http_get.call_args_list,
        )

    def test_demo_url_is_an_https_origin_only(self) -> None:
        self.assertEqual("https://demo.example.org/", validate_demo_url("https://demo.example.org"))
        for invalid in (
            "http://demo.example.org",
            "https://demo.example.org/path",
            "https://user@example.org",
            "https://demo.example.org?token=no",
            "https://stage.papaspyrou.name",
            "https://lxndrp.github.io",
            "https://demo.lzug.repertoire.papaspyrou.name.eastus.azurecontainerapps.io",
            "https://*.repertoire.papaspyrou.name",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(DeploymentError):
                validate_demo_url(invalid)

    def test_workflow_has_minimal_oidc_environment_and_failure_contract(self) -> None:
        workflow = Path(".github/workflows/demo-deploy.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("schedule:", workflow)
        self.assertNotIn("push:\n", workflow)
        self.assertIn("permissions: {}", workflow)
        self.assertIn("actions: read", workflow)
        self.assertIn("contents: read", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("packages: read", workflow)
        self.assertIn("attestations: read", workflow)
        self.assertIn("name: demo", workflow)
        self.assertIn("url: ${{ vars.DEMO_URL }}", workflow)
        self.assertIn("Validate the effective DEMO_URL before Azure mutation", workflow)
        self.assertIn("scripts/validate_demo_url_contract.py validate", workflow)
        self.assertIn('--value "$EFFECTIVE_DEMO_URL"', workflow)
        validation_step = workflow[
            workflow.index(
                "Validate the effective DEMO_URL before Azure mutation"
            ) : workflow.index("Validate protected branch and secret-free inputs")
        ]
        self.assertNotIn("GH_TOKEN", validation_step)
        self.assertNotIn("github.token", validation_step)
        self.assertNotIn("--repository", validation_step)
        self.assertIn("azure/login@f5d393ae46f8fde4be8b75f32e3fc50e654ad0ca", workflow)
        self.assertNotIn("secrets.AZURE", workflow)
        self.assertNotIn("AZURE_CREDENTIALS", workflow)
        self.assertEqual(2, workflow.count("gh attestation verify"))
        self.assertIn('for image in "$APP_IMAGE" "$SEED_IMAGE"', workflow)
        self.assertIn("demo/v*-SNAPSHOT.*)", workflow)
        self.assertIn("demo-snapshot.yml", workflow)
        self.assertIn("demo-publish.yml", workflow)
        self.assertIn("--predicate-type https://cyclonedx.org/bom", workflow)
        self.assertIn("Wait for the new Azure revision to become ready", workflow)
        self.assertIn("Wait separately for application health", workflow)
        self.assertIn("Wait separately for application readiness", workflow)
        self.assertIn("Verify digest-bound pair manifests before Azure mutation", workflow)
        self.assertIn("scripts/verify-demo-image-pair.sh", workflow)
        self.assertLess(
            workflow.index("Verify digest-bound pair manifests before Azure mutation"),
            workflow.index("Log in to Azure using GitHub OIDC"),
        )
        self.assertLess(
            workflow.index("Validate the effective DEMO_URL before Azure mutation"),
            workflow.index("Log in to Azure using GitHub OIDC"),
        )
        self.assertIn(
            "Smoke-test health, readiness, demo API, protected OpenAPI, "
            "and the central frontend route",
            workflow,
        )
        self.assertIn("protected OpenAPI authentication boundary", workflow)
        self.assertIn("if: failure()", workflow)
        self.assertIn("previously verified complete pair", workflow)
        deployment_docs = Path("docs/developers/demo-deployment.md").read_text(encoding="utf-8")
        self.assertIn("HTTP 401", deployment_docs)
        self.assertIn('{"error": "Authentication required."}', deployment_docs)
        publish = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("steps.images.outputs.schema_fingerprint", publish)
        pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        full_quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        pull_request_infra = pull_request.split("\n  infra:\n", 1)[1].split("\n  e2e:\n", 1)[0]
        full_quality_infra = full_quality.split("\n  infra:\n", 1)[1].split("\n  container:\n", 1)[
            0
        ]
        for workflow_infra in (pull_request_infra, full_quality_infra):
            self.assertIn("actions/setup-python@", workflow_infra)
            self.assertIn("astral-sh/setup-uv@", workflow_infra)
            self.assertIn("task quality:infra quality:demo-deployment", workflow_infra)
        self.assertIn("quality:demo-deployment:", taskfile)


if __name__ == "__main__":
    unittest.main()
