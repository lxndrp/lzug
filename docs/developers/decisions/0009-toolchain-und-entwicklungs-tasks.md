# ADR-0009: Toolchain und Entwicklungs-Tasks trennen

## Datum

2026-07-26.

## Status

Akzeptiert.

## Kontext

`mise` verwaltete bisher sowohl die Versionen von Python, Node.js und uv als auch die lokalen Entwicklungsabläufe.
Dadurch vermischte die Toolchain-Datei Umgebungs- und Workflow-Verantwortung.
Die vorhandenen Abläufe für Einrichtung, Tests, Dokumentation, Qualitätssicherung und Entwicklung sollen unverändert bleiben, aber über eine klar erkennbare öffentliche Schnittstelle laufen.

## Entscheidung

`mise` verwaltet ausschließlich die Toolchains Python, Node.js, Go, uv, Task und Syft.
Task und Syft werden über Aqua-Backend-Einträge bereitgestellt.
Syft ersetzt die projektspezifische Lizenzinventur durch standardisierte CycloneDX-Artefakte; diese konkrete Wiederverwendung in lokaler Prüfung, CI und Release belegt den zusätzlichen Toolnutzen.
`Taskfile.yml` ist die einzige öffentliche Schnittstelle für lokale Entwicklungsabläufe; `task setup`, `task test`, `task docs`, `task sbom`, `task quality` und `task dev` sowie ihre dokumentierten Teilaufgaben ersetzen die bisherigen `mise run`-Befehle.

GitHub Actions ist keine lokale Entwickler-Schnittstelle: Die Pipeline modelliert bewusst getrennte Jobs, wählt ihre Jobs konservativ nach Änderungsumfang, nutzt jobspezifische Caches und veröffentlicht Coverage- sowie getrennte Playwright-Artefakte.
Der immer laufende Gesamtstatus und die Pfadklassifikation sind unter
[Pull-Request-Gates](../delivery.md#pull-request-gates) dokumentiert.
Die darin ausgeführten Prüfkommandos entsprechen weiter den lokalen Workflow-Schritten.

## Konsequenzen

Die lokale Einrichtung beginnt mit `mise install` und setzt sich mit `task setup` fort.
Python-Kommandos im Taskfile nutzen `uv run` gegen die gesperrten Entwicklungsabhängigkeiten, Frontend-Aufgaben verwenden ihr Arbeitsverzeichnis und `npm ci`.
Die Einrichtung installiert außerdem den Playwright-Chromium-Browser; `task doctor` prüft Toolchain, virtuelle Python-Umgebung und die verwendete Browser-Executable ohne vollständigen Qualitätslauf.
`task quality` führt Backend, Frontend, Security, Operator-CLI, OCI-Build, standardisierte Dependency-SBOM, Dokumentation und Overall parallel aus.
`task quality:overall` bündelt Container-, Compose-, CLI-zu-Container-, Browser-End-to-End- und Accessibility-Verträge.
Die beiden Browser-Tasks bleiben separat aufrufbar, werden im lokalen Vollauf jedoch seriell ausgeführt.
`task quality:operator` prüft den Go-Vertrag und baut dieselben sechs portablen Ziele wie CI ohne Änderungen an `dist/`.

Die lokale Prüfung wird bewusst nach Risiko und betroffenen Schnittstellen gewählt; Task klassifiziert dafür keine Pfade.
Die Teilaufgaben entsprechen den Qualitätsbereichen aus #230:

| Änderungsumfang | Passende lokale Prüfung |
| --- | --- |
| Technische Dokumentation | `task docs` |
| Eng begrenzter Backend- oder Frontend-Test | `task test:backend` oder `task test:frontend` |
| Produktiver Backend- oder Frontend-Vertrag | Betroffener `quality`-Teil sowie `task docs` und die ausgewählten Untertasks von `task quality:overall` |
| npm-Produktionsabhängigkeiten | `task quality:security` und betroffener Frontend-Teil |
| Operator-CLI | `task test:operator`, bei produktiven Änderungen `task quality:operator` |
| OCI- oder Compose-Konfiguration | `task quality:oci` und die betroffenen Untertasks von `task quality:overall` |
| Unklar, querschnittlich oder Toolchain | `task quality` |

`task quality:oci` baut einmal das lokale Image `lzug:0.0.0-dev.local`.
Container-, Compose- und Betreiber-CLI-Vertrag verwenden dieses Image gemeinsam im Overall-Lauf.
`task quality:compose-config` trennt dabei die generische Standardprüfung über `compose config --quiet` von der kleinen getesteten lzug-Runtime-Policy.
Die Laufzeitprüfungen benötigen eine Docker-kompatible Engine; ihre gemeinsame Orchestrierung unterstützt weiterhin Docker oder Podman und meldet eine fehlende Engine verständlich.
Trivy Config oder Conftest werden mangels zusätzlichem Nachweis gegenüber Compose plus exakter Projektpolicy nicht eingeführt.
Gehostete Trivy-Image- und CodeQL-Scans bleiben bewusst CI-spezifisch.

ADR-0003 bleibt als historische Toolchain-Entscheidung bestehen; dieser ADR ersetzt dessen frühere Zuordnung lokaler Abläufe zu `mise`.

## Alternativen

- Die Abläufe in `mise` belassen: einfach, aber die Verantwortlichkeiten
bleiben vermischt.
- GitHub Actions über `task` ausführen: würde eine zusätzliche Installation
und weniger sichtbare CI-Schritte einführen, ohne die lokale Bedienung zu verbessern.
- Einen weiteren Task-Runner einführen: würde den kleinen Befehlsumfang ohne
erkennbaren Nutzen komplexer machen.

## Referenzen

- [ADR-0003: Toolchain mit mise, uv und npm](0003-toolchain-mise-uv-npm.md)
- [Delivery und Veröffentlichung](../delivery.md)
- [Entwickler-Setup im GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung-Einrichtung)
- [Qualität und Sicherheitsprozess im GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung-Qualitaet-und-Sicherheit)
