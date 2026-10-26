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
            "Eine Runtime gilt nur für die versionierte Kombination aus Host-Betriebssystem und -Version, Architektur, Runtime und unterstützter Runtime-Version als qualifiziert.",
            normalized,
        )
        self.assertIn(
            "freigegebene Versionsbereiche sind ausdrücklich zu dokumentieren.", normalized
        )
        self.assertIn(
            "`CONTAINER_ENGINE` akzeptiert `auto`, `podman`, `apple`, `wslc` oder `docker`.",
            normalized,
        )
        for platform in (
            "| macOS mit Apple Silicon | Apple `container` | Docker |",
            "| Linux | rootless Podman | Docker |",
            "| Windows-Host | Microsoft `wslc` | Docker |",
            "| WSL-Linux-Shell | Linux-Auswahl: Podman, sofern installiert | Docker |",
        ):
            self.assertIn(platform, normalized)
        for row in (
            "| `auto` | Bevorzugte Runtime des Ausführungskontexts |",
            "| `podman` | Podman |",
            "| `apple` | Apple `container` |",
            "| `wslc` | Microsoft `wslc` |",
            "| `docker` | Docker |",
        ):
            self.assertIn(row, normalized)
        self.assertIn(
            "In `auto` darf Docker nur gewählt werden, wenn die bevorzugte Runtime fehlt.",
            normalized,
        )
        self.assertIn(
            "Eine explizit gewählte Runtime, die nicht installiert, nicht erreichbar oder für die erkannte Host-/Runtimeversion nicht qualifiziert ist, führt zum Abbruch.",
            normalized,
        )
        self.assertIn(
            "Ist sie installiert, aber nicht qualifiziert, bricht `auto` mit einer Diagnose ab; ein Wechsel erfordert dann eine explizite Wahl `CONTAINER_ENGINE=docker`.",
            normalized,
        )
        self.assertIn(
            "Ein unerreichbarer Dienst, Buildfehler oder Containerstartfehler führt nicht zum Runtimewechsel.",
            normalized,
        )
        self.assertIn("Der Runtimevertrag erstellt den Buildkandidaten einmal.", normalized)
        self.assertIn(
            "Ein impliziter Zugriff auf einen enginespezifischen Imagespeicher oder ein zweiter Build ist kein Übergabevertrag.",
            normalized,
        )
        self.assertIn("als Archiv exportiert", normalized)
        for row in (
            "| `lzug-app` | Aus dem Archiv des gebauten Images | Gemeinsamer App-Runtimevertrag mit genau diesem Image |",
            "| `lzug-demo-app` | Aus dem Archiv des gebauten Images | Demo-Runtimevertrag mit genau diesem Image und dem zugehörigen Seed |",
            "| `lzug-demo-seed` | Aus dem Archiv des gebauten Images | SQLite-Datei und Manifest aus genau diesem Image extrahieren und Identität, Produktrevision, Runtimevertrag sowie Schemafingerabdruck prüfen; Seed nicht als eigenständigen Server starten |",
        ):
            self.assertIn(row, normalized)
        self.assertIn("Seed nicht als eigenständigen Server starten", normalized)
        self.assertIn("Daten-Roundtrip und Persistenz bei Restart/Stop-Start", normalized)
        self.assertIn("lzug-codex-<scope>", normalized)
        self.assertIn(
            "Temporäre Ressourcen eines Worktree-Tests verwenden Namen der Form `lzug-codex-<scope>-<rolle>`.",
            normalized,
        )
        self.assertIn(
            "Container, Images, Volumes und Netzwerke erhalten zusätzlich genau das Worktree-Label `lzug-codex-<scope>`.",
            normalized,
        )
        self.assertIn("bricht Anlage beziehungsweise Cleanup vor Änderungen ab", normalized)
        self.assertIn("Persistente Anwendungsdatenvolumes bleiben unlabeled", normalized)
        self.assertIn(
            "Cleanup entfernt ausschließlich Ressourcen mit dem exakten Label und dem erwarteten Namenspräfix.",
            normalized,
        )
        self.assertIn(
            "Globales `prune` und das Entfernen fremder Volumes sind unzulässig.",
            normalized,
        )
        self.assertIn(
            "Docker Compose, seine Konfigurationsprüfung und Docker-basierte Veröffentlichungs- sowie CI-Schritte bleiben Docker-spezifische Referenzprüfungen und ersetzen keinen plattformneutralen Runtime-Nachweis.",
            normalized,
        )
        self.assertIn(
            "ADR-0033 bleibt für Prozess, Persistenz, Admintransport und Lifecycle maßgeblich",
            normalized,
        )


if __name__ == "__main__":
    unittest.main()
