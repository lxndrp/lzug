from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


class ComponentConfigLayoutTests(unittest.TestCase):
    def test_component_taskfiles_are_included_from_the_root_aggregator(self) -> None:
        taskfile = Path("Taskfile.yml").read_text(encoding="utf-8")

        for path in (
            "backend/Taskfile.yml",
            "delivery/Taskfile.yml",
            "demo/Taskfile.yml",
            "docs/Taskfile.yml",
            "frontend/Taskfile.yml",
            "operator-cli/Taskfile.yml",
        ):
            with self.subTest(path=path):
                self.assertIn(f"taskfile: {path}", taskfile)

        for task in (
            "backend:test",
            "delivery:test",
            "demo:test",
            "docs:build",
            "frontend:test",
            "operator:test",
        ):
            with self.subTest(task=task):
                self.assertIn(task, taskfile)

    def test_component_owned_configuration_is_not_left_at_the_root(self) -> None:
        self.assertFalse(Path(".node-version").exists())
        self.assertFalse(Path("mkdocs.yml").exists())
        self.assertFalse(Path("Dockerfile.demo").exists())
        self.assertFalse(Path("Dockerfile.demo-seed").exists())

        for path in (
            "frontend/.node-version",
            "docs/mkdocs.yml",
            "demo/containers/Dockerfile.demo",
            "demo/containers/Dockerfile.demo-seed",
        ):
            with self.subTest(path=path):
                self.assertTrue(Path(path).is_file())

    def test_component_taskfiles_own_packaging_build_and_publication_flows(self) -> None:
        operator = Path("operator-cli/Taskfile.yml").read_text(encoding="utf-8")
        delivery = Path("delivery/Taskfile.yml").read_text(encoding="utf-8")
        demo = Path("demo/Taskfile.yml").read_text(encoding="utf-8")
        docs = Path("docs/Taskfile.yml").read_text(encoding="utf-8")
        frontend = Path("frontend/Taskfile.yml").read_text(encoding="utf-8")
        frontend_adapter = Path("scripts/build-frontend.ps1").read_text(encoding="utf-8")
        root = Path("Taskfile.yml").read_text(encoding="utf-8")

        self.assertIn("packaging-and-reproducibility", operator)
        self.assertIn("operator-reproducibility.ps1", operator)
        self.assertIn("quality:image", delivery)
        self.assertIn("syft", delivery)
        self.assertIn("seed_revision=$(jq -er", demo)
        self.assertIn("scripts/demo-container-smoke.sh", demo)
        self.assertIn("  publication:", docs)
        self.assertIn("hugo --source docs/publication", docs)
        self.assertIn("backend.fastapi_assembly", docs)
        self.assertIn("typedoc", docs)
        self.assertIn("production-build:", frontend)
        self.assertIn("run: once", frontend)
        self.assertIn("- transport:generate", frontend)
        self.assertNotIn("Invoke-Native 'task'", frontend_adapter)
        self.assertIn("- frontend:production-build", root)
        self.assertIn("- task: frontend:e2e:development", root)
        self.assertIn("- task: frontend:e2e:production", root)

    def test_shared_and_standard_root_entries_remain_available(self) -> None:
        for path in (
            ".mise.toml",
            ".python-version",
            ".env.example",
            ".dockerignore",
            "Dockerfile",
            "Taskfile.yml",
            "compose.yaml",
            "pyproject.toml",
            "uv.lock",
        ):
            with self.subTest(path=path):
                self.assertTrue(Path(path).is_file())

    def test_shared_tool_versions_are_explicit(self) -> None:
        config = tomllib.loads(Path(".mise.toml").read_text(encoding="utf-8"))

        for tool, version in config["tools"].items():
            with self.subTest(tool=tool):
                self.assertIsInstance(version, str)
                self.assertNotIn(version.lower(), {"latest", "main", "master"})

    def test_backend_uses_component_local_src_and_database_resources(self) -> None:
        self.assertTrue(Path("backend/src/backend/__init__.py").is_file())
        self.assertTrue(Path("backend/db/schema.sql").is_file())
        self.assertFalse(list(Path("backend").glob("*.py")))
        self.assertFalse(Path("db").exists())

        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('package-dir = {"" = "backend/src"}', pyproject)
        self.assertIn('where = ["backend/src"]', pyproject)

        for path in (
            "Dockerfile",
            "demo/containers/Dockerfile.demo",
            "demo/containers/Dockerfile.demo-seed",
        ):
            dockerfile = Path(path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("uv build --wheel --out-dir /dist", dockerfile)
                self.assertIn("backend/src", dockerfile)
                self.assertIn("backend/db", dockerfile)
                self.assertNotIn("backend/application.py", dockerfile)


if __name__ == "__main__":
    unittest.main()
