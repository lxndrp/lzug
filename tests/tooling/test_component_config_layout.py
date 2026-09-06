from __future__ import annotations

import unittest
from pathlib import Path


class ComponentConfigLayoutTests(unittest.TestCase):
    def test_component_owned_configuration_is_not_left_at_the_root(self) -> None:
        self.assertFalse(Path(".node-version").exists())
        self.assertFalse(Path("mkdocs.yml").exists())
        self.assertFalse(Path("Dockerfile.demo").exists())
        self.assertFalse(Path("Dockerfile.demo-seed").exists())

        for path in (
            "frontend/.node-version",
            "docs/mkdocs.yml",
            "demo/Dockerfile.demo",
            "demo/Dockerfile.demo-seed",
        ):
            with self.subTest(path=path):
                self.assertTrue(Path(path).is_file())

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

    def test_backend_uses_component_local_src_and_database_resources(self) -> None:
        self.assertTrue(Path("backend/src/backend/__init__.py").is_file())
        self.assertTrue(Path("backend/db/schema.sql").is_file())
        self.assertFalse(list(Path("backend").glob("*.py")))
        self.assertFalse(Path("db").exists())

        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('package-dir = {"" = "backend/src"}', pyproject)
        self.assertIn('where = ["backend/src"]', pyproject)

        for path in ("Dockerfile", "demo/Dockerfile.demo", "demo/Dockerfile.demo-seed"):
            dockerfile = Path(path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                self.assertIn("uv build --wheel --out-dir /dist", dockerfile)
                self.assertIn("backend/src", dockerfile)
                self.assertIn("backend/db", dockerfile)
                self.assertNotIn("backend/application.py", dockerfile)


if __name__ == "__main__":
    unittest.main()
