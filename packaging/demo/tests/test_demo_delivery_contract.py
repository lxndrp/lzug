import unittest
from pathlib import Path


class DemoDeliveryContractTests(unittest.TestCase):
    def test_platform_workflows_use_immutable_oci_inputs(self) -> None:
        deploy = Path(".github/workflows/demo-deploy.yml").read_text(encoding="utf-8")
        publish = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("gh attestation verify", deploy)
        self.assertIn("sha256:", deploy)
        self.assertIn("docker buildx imagetools inspect", publish)

    def test_entrypoints_and_shared_phases(self) -> None:
        workflows = {path.name for path in Path(".github/workflows").glob("*.yml")}
        self.assertIn("release.yml", workflows)
        self.assertIn("snapshot.yml", workflows)
        for name in ("release.yml", "snapshot.yml"):
            text = Path(".github/workflows", name).read_text(encoding="utf-8")
            self.assertIn("product-publish.yml", text)
            self.assertIn("demo-publish.yml", text)
            self.assertIn("demo-deploy.yml", text)

    def test_two_channel_publish_contracts(self) -> None:
        product = Path(".github/workflows/product-publish.yml").read_text(encoding="utf-8")
        demo = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_call:", product)
        self.assertIn("inputs.channel == 'stable'", product)
        self.assertIn("inputs.channel == 'snapshot'", product)
        self.assertIn("channel:", demo)
        self.assertIn('if test "$CHANNEL" = snapshot', demo)
        self.assertIn("python3 -m backend.version", demo)

    def test_snapshot_namespace_is_consistent(self) -> None:
        for path in (
            "backend/src/backend/version.py",
            "deployment/demo/infra/variables.tf",
            "deployment/demo/infra/main.tf",
        ):
            self.assertIn("snapshot/", Path(path).read_text(encoding="utf-8"))

    def test_quality_smoke_resources_use_the_worktree_scope(self) -> None:
        taskfile = Path("packaging/demo/Taskfile.yml").read_text(encoding="utf-8")
        smoke = Path("packaging/demo/container-smoke.sh").read_text(encoding="utf-8")

        self.assertIn('resource_label="${LZUG_QUALITY_RESOURCE_LABEL:-}"', taskfile)
        self.assertIn(
            'seed_container_name="$resource_prefix-demo-seed-extract-${temporary_directory##*/}"',
            taskfile,
        )
        self.assertIn(
            'docker create --name "$seed_container_name" --label "$resource_label" "$seed_image"',
            taskfile,
        )
        self.assertIn('suffix="$resource_label-demo-smoke-$run_id"', smoke)
        self.assertIn('docker volume create --label "$resource_label" "$volume"', smoke)
        self.assertIn('docker run --name "$run_name" --label "$resource_label" "$@"', smoke)
        self.assertEqual(smoke.count("docker run "), 2)
        self.assertIn('docker_run "$suffix-seed-$seed_run"', smoke)
        self.assertIn('docker_run "$container" --detach', smoke)
        self.assertIn('docker_run "$suffix-product-check" --rm', smoke)
        self.assertIn('docker rm --force "$container_id"', smoke)
        self.assertIn('if [ "$volume_created" -eq 1 ]; then', smoke)


if __name__ == "__main__":
    unittest.main()
