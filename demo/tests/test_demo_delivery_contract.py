import unittest
from pathlib import Path


class DemoDeliveryContractTests(unittest.TestCase):
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
        self.assertIn('--channel "$CHANNEL"', demo)

    def test_snapshot_namespace_is_consistent(self) -> None:
        for path in (
            "backend/src/backend/build_metadata.py",
            "demo/infra/variables.tf",
            "demo/infra/main.tf",
        ):
            self.assertIn("snapshot/", Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
