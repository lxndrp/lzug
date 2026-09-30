# ADR-0009: Toolchain und Entwicklungs-Tasks trennen

## Datum

2026-07-26.

## Status

Akzeptiert.
Die öffentliche Taskgrenze gilt fort; die konkreten Zuständigkeiten aus
früheren Abschnitten werden durch ADR-0039 präzisiert.

## Kontext

`mise` verwaltete bisher sowohl die Versionen von Python, Node.js und uv als auch die lokalen Entwicklungsabläufe.
Dadurch vermischte die Toolchain-Datei Umgebungs- und Workflow-Verantwortung.
Die vorhandenen Abläufe für Einrichtung, Tests, Dokumentation, Qualitätssicherung und Entwicklung sollen unverändert bleiben, aber über eine klar erkennbare öffentliche Schnittstelle laufen.

## Entscheidung

Diese Entscheidung trennt die Werkzeugbereitstellung von den öffentlichen
Entwicklungsabläufen: `mise` stellt gepinnte Werkzeuge bereit, `Task` ist die
einzige öffentliche Schnittstelle für lokale Entwicklungsabläufe.
Die aktuelle Zuordnung nativer Konfiguration, Standardaufrufe und verbleibender
Logik folgt [ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md).
Die konkrete Bereitstellung und verfügbaren Tasks stehen in
[Entwicklung](../development.md); dieser ADR legt keine heutige Werkzeugliste,
SBOM-Auswahl oder Quality-Aufgabenfolge fest.

GitHub Actions ist keine lokale Entwickler-Schnittstelle.
Auslöser, Runner, Berechtigungen und CI-Nachweise bleiben Plattformaufgaben;
die aktuellen Pull-Request-Gates stehen unter
[Delivery und Veröffentlichung](../delivery.md#pull-request-gates).

## Konsequenzen

Die jeweils aktuelle lokale Einrichtung, Testauswahl und Taskliste stehen in
[Entwicklung](../development.md) und im Taskgraph.
Prüftiefe folgt Risiko und betroffenen Schnittstellen; Task klassifiziert dafür
keine Pfade.
Diese Entscheidung dupliziert weder eine Taskliste noch eine zweite
Qualitäts- oder Artefaktpolicy.
Die aktuelle Zuordnung von Standardwerkzeugen und gegebenenfalls nötigen
Adaptern folgt ADR-0039.

ADR-0003 hält die ursprüngliche Werkzeugwahl fest.
Die übergreifende, aktuell geltende Zuordnung von Werkzeugversionen,
Paketabhängigkeiten, Taskgraph, Plattformaufgaben und verbleibender Logik
steht in [ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md) und hat
Vorrang vor früheren Einzelzuordnungen dieses ADRs.

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
- [Entwicklung](../development.md)
