import unittest
from pathlib import Path


class DemoDeliveryContractTests(unittest.TestCase):
    def test_platform_delivery_has_no_python_host_adapters(self) -> None:
        for path in (
            "scripts/demo_snapshot.py",
            "scripts/demo_deployment.py",
            "scripts/verify-demo-image-pair.sh",
            "demo/delivery/contract.py",
        ):
            with self.subTest(path=path):
                self.assertFalse(Path(path).exists())

    def test_platform_workflows_use_immutable_oci_inputs(self) -> None:
        deploy = Path(".github/workflows/demo-deploy.yml").read_text(encoding="utf-8")
        publish = Path(".github/workflows/demo-publish.yml").read_text(encoding="utf-8")
        self.assertIn("gh attestation verify", deploy)
        self.assertIn("az containerapp update", deploy)
        self.assertIn("sha256:", deploy)
        self.assertIn("docker buildx imagetools inspect", publish)
        self.assertNotIn("demo.delivery.contract", deploy)
        self.assertNotIn("demo.delivery.contract", publish)

    def test_entrypoints_and_shared_phases(self) -> None:
        workflows = {path.name for path in Path(".github/workflows").glob("*.yml")}
        self.assertIn("release.yml", workflows)
        self.assertIn("snapshot.yml", workflows)
        self.assertNotIn("demo-promote.yml", workflows)
        self.assertNotIn("demo-snapshot.yml", workflows)
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
        self.assertIn("scripts/build_metadata.py", demo)

    def test_snapshot_namespace_is_consistent(self) -> None:
        for path in (
            "backend/src/backend/build_metadata.py",
            "demo/infra/variables.tf",
            "demo/infra/main.tf",
        ):
            self.assertIn("snapshot/", Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
