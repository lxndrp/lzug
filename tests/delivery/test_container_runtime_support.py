from __future__ import annotations

import unittest
from pathlib import Path


class ContainerRuntimeSupportTests(unittest.TestCase):
    def test_local_runtime_and_production_scopes_are_separate(self) -> None:
        decision = Path(
            "docs/developers/decisions/0043-lokale-oci-runtimes-und-plattformqualifikation.md"
        ).read_text(encoding="utf-8")

        normalized = " ".join(decision.split())
        self.assertIn(
            "Für zentrale CI, Release und Self-Hosting bleibt Docker Engine auf Linux die qualifizierte Referenz.",
            normalized,
        )
        self.assertIn("Apple `container`", normalized)
        self.assertIn("rootless Podman", normalized)
        self.assertIn("Microsoft `wslc`", normalized)
        self.assertIn("Nachweise werden getrennt in #939, #940 und #941 geführt.", normalized)
        self.assertIn(
            "`CONTAINER_ENGINE` akzeptiert `auto`, `podman`, `apple`, `wslc` oder `docker`.",
            normalized,
        )
        for row in (
            "| `auto` | Bevorzugte Runtime des Ausführungskontexts |",
            "| `podman` | Podman |",
            "| `apple` | Apple `container` |",
            "| `wslc` | Microsoft `wslc` |",
            "| `docker` | Docker |",
        ):
            self.assertIn(row, normalized)
        self.assertIn("führt nicht zum Runtimewechsel", normalized)
        self.assertIn("als Archiv exportiert", normalized)
        for image in ("lzug-app", "lzug-demo-app", "lzug-demo-seed"):
            self.assertIn(f"| `{image}` |", normalized)
        self.assertIn("Seed nicht als eigenständigen Server starten", normalized)
        self.assertIn("lzug-codex-<scope>", normalized)
        self.assertIn("bricht Anlage beziehungsweise Cleanup vor Änderungen ab", normalized)
        self.assertIn("Persistente Anwendungsdatenvolumes bleiben unlabeled", normalized)
        self.assertIn("Globales `prune`", normalized)
        self.assertIn("Docker Compose", normalized)
        self.assertIn(
            "ADR-0033 bleibt für Prozess, Persistenz, Admintransport und Lifecycle maßgeblich",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
