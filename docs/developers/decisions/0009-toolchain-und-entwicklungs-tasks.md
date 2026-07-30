# ADR-0009: Toolchain und Entwicklungs-Tasks trennen

## Status

Akzeptiert am 26.07.2026.

## Kontext

`mise` verwaltete bisher sowohl die Versionen von Python, Node.js und uv als
auch die lokalen Entwicklungsabläufe. Dadurch vermischte die Toolchain-Datei
Umgebungs- und Workflow-Verantwortung. Die vorhandenen Abläufe für Einrichtung,
Tests, Dokumentation, Qualitätssicherung und Entwicklung sollen unverändert
bleiben, aber über eine klar erkennbare öffentliche Schnittstelle laufen.

## Entscheidung

`mise` verwaltet ausschließlich die Toolchains Python, Node.js, uv und Task.
Task wird über den Aqua-Backend-Eintrag `aqua:go-task/task` bereitgestellt.
`Taskfile.yml` ist die einzige öffentliche Schnittstelle für lokale
Entwicklungsabläufe; `task setup`, `task test`, `task docs`, `task quality` und
`task dev` sowie ihre dokumentierten Teilaufgaben ersetzen die bisherigen
`mise run`-Befehle.

GitHub Actions bleibt unverändert. Die Pipeline ist keine lokale
Entwickler-Schnittstelle: Sie modelliert bewusst getrennte Jobs, nutzt
jobspezifische Caches und veröffentlicht Coverage- sowie getrennte
Playwright-Artefakte. Die darin ausgeführten Prüfkommandos entsprechen weiter
den lokalen Workflow-Schritten.

## Konsequenzen

Die lokale Einrichtung beginnt mit `mise install` und setzt sich mit
`task setup` fort. Python-Kommandos im Taskfile nutzen `uv run` gegen die
gesperrten Entwicklungsabhängigkeiten, Frontend-Aufgaben verwenden ihr
Arbeitsverzeichnis und `npm ci`. Die Einrichtung installiert außerdem den
Playwright-Chromium-Browser; `task doctor` prüft Toolchain, virtuelle
Python-Umgebung und die verwendete Browser-Executable ohne vollständigen
Qualitätslauf. `task quality` behält die parallele Ausführung der bisherigen
Prüfabschnitte bei und führt Browser-End-to-End- sowie Accessibility-Prüfungen
parallel aus.

ADR-0003 bleibt als historische Toolchain-Entscheidung bestehen; dieser ADR
ersetzt dessen frühere Zuordnung lokaler Abläufe zu `mise`.

## Alternativen

- Die Abläufe in `mise` belassen: einfach, aber die Verantwortlichkeiten
  bleiben vermischt.
- GitHub Actions über `task` ausführen: würde eine zusätzliche Installation
  und weniger sichtbare CI-Schritte einführen, ohne die lokale Bedienung zu
  verbessern.
- Einen weiteren Task-Runner einführen: würde den kleinen Befehlsumfang ohne
  erkennbaren Nutzen komplexer machen.

## Referenzen

- [ADR-0003: Toolchain mit mise, uv und npm](0003-toolchain-mise-uv-npm.md)
- [Entwickler-Setup im GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung-Einrichtung)
- [Qualität und Sicherheitsprozess im GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung-Qualitaet-und-Sicherheit)
