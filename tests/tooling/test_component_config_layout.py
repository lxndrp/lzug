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

    def test_shared_tool_versions_are_explicit(self) -> None:
        config = tomllib.loads(Path(".mise.toml").read_text(encoding="utf-8"))

        for tool, version in config["tools"].items():
            with self.subTest(tool=tool):
                self.assertIsInstance(version, str)
                self.assertNotIn(version.lower(), {"latest", "main", "master"})


if __name__ == "__main__":
    unittest.main()
