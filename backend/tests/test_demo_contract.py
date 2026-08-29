from __future__ import annotations

import copy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from demo.contract import (
    CANONICAL_DEMO_URL,
    RUNTIME_CONTRACT,
    DemoArtifactPair,
    DemoContractError,
    canonical_digest,
    demo_identity,
    main,
    validate_deployment_source,
    validate_manifest,
    validate_manifest_pair,
    validate_public_demo_url,
)


class DemoContractTests(unittest.TestCase):
    release_tag = "v0.4.0"
    release_commit = "a" * 40
    snapshot_tag = "demo/v0.4.0-SNAPSHOT.abcdef0"
    snapshot_commit = "abcdef0" + "b" * 33

    def manifests(self) -> tuple[dict, dict]:
        product = demo_identity(self.release_tag, self.release_commit).product
        seed_binding = {
            "manifest_version": 1,
            "product": product,
            "runtime_contract": RUNTIME_CONTRACT,
            "schema": {"fingerprint": "c" * 64},
        }
        seed = {**seed_binding, "seed_revision": canonical_digest(seed_binding)}
        app = {
            "manifest_version": 1,
            "product": product,
            "runtime_contract": RUNTIME_CONTRACT,
            "schema": {"fingerprint": "c" * 64},
            "seed_revision": seed["seed_revision"],
        }
        return app, seed

    def pair(self, **overrides: str) -> DemoArtifactPair:
        values = {
            "app_image": "ghcr.io/lxndrp/lzug-demo-app@sha256:" + "1" * 64,
            "seed_image": "ghcr.io/lxndrp/lzug-demo-seed@sha256:" + "2" * 64,
            "product_tag": self.release_tag,
            "product_commit": self.release_commit,
            "runtime_contract": RUNTIME_CONTRACT,
            "schema_fingerprint": "c" * 64,
            "seed_revision": "d" * 64,
        }
        return DemoArtifactPair(**(values | overrides))

    def test_release_and_snapshot_use_the_same_identity_boundary(self) -> None:
        release = demo_identity(self.release_tag, self.release_commit, "stable")
        snapshot = demo_identity(self.snapshot_tag, self.snapshot_commit, "snapshot")

        self.assertEqual("0.4.0", release.identity)
        self.assertEqual("release", release.channel)
        self.assertEqual("v0.4.0-SNAPSHOT@abcdef0", snapshot.identity)
        self.assertEqual("v0.4.0-SNAPSHOT-abcdef0", snapshot.oci_tag)

        for tag, commit, channel in (
            (self.snapshot_tag, self.snapshot_commit, "stable"),
            (self.release_tag, self.release_commit, "snapshot"),
            ("v0.4.0-rc.1", self.release_commit, "stable"),
            (self.snapshot_tag, "0" * 40, "snapshot"),
        ):
            with self.subTest(tag=tag, channel=channel), self.assertRaises(DemoContractError):
                demo_identity(tag, commit, channel)  # type: ignore[arg-type]

    def test_public_url_rules_have_one_general_and_one_repository_constraint(self) -> None:
        self.assertEqual(
            CANONICAL_DEMO_URL + "/",
            validate_public_demo_url(CANONICAL_DEMO_URL, require_canonical=True),
        )
        self.assertEqual(
            "https://demo.example.org/", validate_public_demo_url("https://demo.example.org")
        )

        for invalid in (
            "http://demo.example.org",
            "https://demo.example.org/path",
            "https://user@example.org",
            "https://stage.papaspyrou.name",
            "https://demo.example.azurecontainerapps.io",
            "https://*.example.org",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(DemoContractError):
                validate_public_demo_url(invalid)
        with self.assertRaisesRegex(DemoContractError, "confirmed repository"):
            validate_public_demo_url("https://demo.example.org", require_canonical=True)

    def test_pair_contract_rejects_moving_or_cross_product_inputs(self) -> None:
        pair = self.pair()
        pair.validate()
        self.assertEqual("lxndrp/lzug/.github/workflows/demo-publish.yml", pair.signer_workflow)
        snapshot_pair = self.pair(
            product_tag=self.snapshot_tag, product_commit=self.snapshot_commit
        )
        self.assertEqual(
            "lxndrp/lzug/.github/workflows/demo-snapshot.yml",
            snapshot_pair.signer_workflow,
        )

        for overrides in (
            {"app_image": "ghcr.io/lxndrp/lzug-demo-app:latest"},
            {"seed_image": "ghcr.io/example/lzug-demo-seed@sha256:" + "2" * 64},
            {"product_commit": "A" * 40},
            {"runtime_contract": "legacy-health-only"},
            {"schema_fingerprint": "short"},
            {"seed_revision": "short"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(DemoContractError):
                self.pair(**overrides).validate()

    def test_manifest_pair_uses_one_product_schema_runtime_and_seed_contract(self) -> None:
        app, seed = self.manifests()
        validate_manifest_pair(
            app,
            seed,
            expected_product_tag=self.release_tag,
            expected_product_commit=self.release_commit,
            expected_runtime_contract=RUNTIME_CONTRACT,
            expected_schema_fingerprint="c" * 64,
            expected_seed_revision=seed["seed_revision"],
        )

        mutations = (
            ("non-canonical product", "app", ("product", "identity"), "invented"),
            ("schema", "app", ("schema", "fingerprint"), "e" * 64),
            ("runtime", "app", ("runtime_contract",), "legacy-health-only"),
            ("seed", "app", ("seed_revision",), "f" * 64),
            ("binding", "seed", ("schema", "fingerprint"), "e" * 64),
        )
        for label, target, path, value in mutations:
            changed_app = copy.deepcopy(app)
            changed_seed = copy.deepcopy(seed)
            manifest = changed_app if target == "app" else changed_seed
            cursor = manifest
            for key in path[:-1]:
                cursor = cursor[key]
            cursor[path[-1]] = value
            with self.subTest(label=label), self.assertRaises(DemoContractError):
                validate_manifest_pair(
                    changed_app,
                    changed_seed,
                    expected_product_tag=self.release_tag,
                    expected_product_commit=self.release_commit,
                    expected_runtime_contract=RUNTIME_CONTRACT,
                    expected_schema_fingerprint="c" * 64,
                    expected_seed_revision=seed["seed_revision"],
                )

        self.assertEqual(app, validate_manifest(app, "app"))
        self.assertEqual(seed, validate_manifest(seed, "seed"))

    def test_deploy_and_rollback_sources_share_the_identity_contract(self) -> None:
        validate_deployment_source(
            promotion_channel="stable",
            operation="deploy",
            product_tag=self.release_tag,
            product_commit=self.release_commit,
            github_ref="refs/heads/master",
        )
        validate_deployment_source(
            promotion_channel="snapshot",
            operation="deploy",
            product_tag=self.snapshot_tag,
            product_commit=self.snapshot_commit,
            github_ref=f"refs/tags/{self.snapshot_tag}",
        )
        validate_deployment_source(
            promotion_channel="",
            operation="rollback",
            product_tag=self.release_tag,
            product_commit=self.release_commit,
            github_ref="refs/heads/master",
        )

        invalid = (
            ("stable", "rollback", self.release_tag, "refs/heads/master"),
            ("snapshot", "deploy", self.snapshot_tag, "refs/heads/master"),
            ("", "rollback", self.release_tag, "refs/heads/feature"),
        )
        for channel, operation, tag, github_ref in invalid:
            commit = self.snapshot_commit if channel == "snapshot" else self.release_commit
            with (
                self.subTest(channel=channel, operation=operation),
                self.assertRaises(DemoContractError),
            ):
                validate_deployment_source(
                    promotion_channel=channel,
                    operation=operation,
                    product_tag=tag,
                    product_commit=commit,
                    github_ref=github_ref,
                )

    def test_cli_exposes_the_same_identity_url_and_pair_contract(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            result = main(
                [
                    "identity",
                    "--tag",
                    self.snapshot_tag,
                    "--commit",
                    self.snapshot_commit,
                    "--channel",
                    "snapshot",
                    "--field",
                    "oci_tag",
                ]
            )
        self.assertEqual(0, result)
        self.assertEqual("v0.4.0-SNAPSHOT-abcdef0", stdout.getvalue().strip())

        pair = self.pair()
        pair_args = [
            "--app-image",
            pair.app_image,
            "--seed-image",
            pair.seed_image,
            "--product-tag",
            pair.product_tag,
            "--product-commit",
            pair.product_commit,
            "--runtime-contract",
            pair.runtime_contract,
            "--schema-fingerprint",
            pair.schema_fingerprint,
            "--seed-revision",
            pair.seed_revision,
        ]
        self.assertEqual(0, main(["validate-pair", *pair_args]))

        stderr = StringIO()
        with redirect_stderr(stderr):
            result = main(["validate-url", "--canonical", "--value", "https://demo.example.org"])
        self.assertEqual(1, result)
        self.assertIn("confirmed repository", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
