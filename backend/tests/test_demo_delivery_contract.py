from __future__ import annotations

import unittest
from pathlib import Path


class DemoDeliveryContractTests(unittest.TestCase):
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

    def test_complete_quality_includes_demo_pair(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")
        pull_request = Path(".github/workflows/pull-request.yml").read_text(encoding="utf-8")
        quality = Path(".github/workflows/quality.yml").read_text(encoding="utf-8")

        self.assertIn("quality:demo:", taskfile)
        self.assertIn("scripts/demo-container-smoke.sh", taskfile)
        self.assertIn("quality:demo", pull_request)
        self.assertIn("quality:demo", quality)


if __name__ == "__main__":
    unittest.main()
