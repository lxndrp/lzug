from __future__ import annotations

import unittest
from pathlib import Path


class ContainerRuntimeSupportTests(unittest.TestCase):
    def test_local_runtime_and_production_scopes_are_separate(self) -> None:
        decision = Path(
            "docs/developers/decisions/0033-aio-betrieb-admintransport-und-lifecycle.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "Docker Engine auf Linux bleibt die qualifizierte Referenz für zentrale CI,\n"
            "Release und Self-Hosting.",
            decision,
        )
        self.assertIn("Apple `container`", decision)
        self.assertIn("rootless Podman", decision)
        self.assertIn("Microsoft `wslc`", decision)
        self.assertIn("vorliegen", decision)
        self.assertIn("`CONTAINER_ENGINE` steuert die Runtimeauswahl", decision)
        for value in ("auto", "podman", "apple", "wslc", "docker"):
            self.assertIn(f"| `{value}` |", decision)
        self.assertIn("| `apple` | Apple `container` |", decision)
        self.assertIn("| `wslc` | Microsoft `wslc` |", decision)
        self.assertIn("Eine installierte, aber nicht erreichbare Runtime", decision)
        self.assertIn("Image-Archiv", decision)
        self.assertIn("lzug-codex-<scope>", decision)
        self.assertIn("bricht die Anlage beziehungsweise das", decision)
        self.assertIn("Persistente Anwendungsdatenvolumes bleiben unlabeled", decision)
        self.assertIn("kein globales `prune`", decision)
        self.assertIn("Docker Compose", decision)
        self.assertIn("ADR-0014", decision)


if __name__ == "__main__":
    unittest.main()
