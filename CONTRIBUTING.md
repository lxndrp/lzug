# Zu lzug beitragen

Danke für Beiträge zu `lzug`. Dieses Dokument beschreibt die lokale
Entwicklung; fachliche Prioritäten und Akzeptanzkriterien bleiben in den
[GitHub Issues](https://github.com/lxndrp/lzug/issues). Die Maintainer pflegen
die operative Reihenfolge zusätzlich im GitHub Project `lzug Roadmap`.

`lzug` ist ein ausdrücklich nicht produktionsreifer Quellcode-Prototyp mit
synthetischen Demo- und Testdaten. Das Projekt ist nicht offiziell mit der IHK
verbunden. Beiträge dürfen daher keine Produktionsreife, IHK-Zugehörigkeit oder
produktive Betriebszusage voraussetzen.

## Voraussetzungen und Einrichtung

Die projektweit festgelegten Werkzeuge werden von [mise](https://mise.jdx.dev/)
verwaltet. Dazu gehören Python, Node.js, uv und Task. Nach der Installation von
mise:

```sh
mise install
task setup
```

`task setup` erstellt die Python-Umgebung aus `uv.lock` und installiert die
Frontend-Abhängigkeiten mit npm. Das Projekt verwendet npm und
`frontend/package-lock.json`; pnpm wird nicht verwendet.

## Lokal entwickeln

Backend und Angular-Frontend gemeinsam starten:

```sh
task dev
```

Die JSON-API läuft unter `http://127.0.0.1:8000/api/`. Ihre verbindliche
Beschreibung ist unter `http://127.0.0.1:8000/api/openapi.json` verfügbar,
Swagger UI unter `http://127.0.0.1:8000/api/docs`. Das Frontend ist unter
`http://localhost:4200/` erreichbar und leitet `/api` über den lokalen Proxy
an das Backend weiter.

## Qualität und Dokumentation

Vor einem Pull Request die betroffenen Prüfungen und anschließend den
vollständigen Lauf ausführen:

```sh
task quality
```

Der Lauf enthält Backend-Linting, Formatierung, Sicherheitsprüfung, Tests und
Coverage, Frontend-Linting, Produktionsbuild und Tests sowie Browser- und
Accessibility-Prüfungen. Die vollständige Dokumentation mit Python- und
TypeScript-Referenzen entsteht mit `task docs`.

Frontend-spezifische Befehle und die E2E-Isolation beschreibt
[frontend/README.md](frontend/README.md). Architektur, API-Vertrag,
Dokumentationsstandard und der vollständige [Arbeitsprozess](docs/developers/arbeitsprozess.md)
stehen im [Entwicklerhandbuch](docs/developers/index.md).

Das öffentliche redaktionelle Handbuch liegt ausschließlich im separaten
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki) und wird nicht in diesem
Repository gespiegelt. Wiki-Änderungen werden in einem separaten Clone mit dem
manuellen `Wiki pre-publish check` gegen einen konkreten Branch oder Commit
geprüft und erst nach Maintainer-Freigabe in den Default-Branch veröffentlicht.
Der genaue Ablauf steht in der [Wiki-Publikation](docs/developers/wiki-publishing.md).

## Änderungen einreichen

- Arbeit zu einem Issue erfolgt auf einem eigenen Branch
  `codex/<issue>-<kurzer-name>`.
- Änderungen klein und thematisch zusammenhängend halten; Commit-Nachrichten
  werden auf Englisch geschrieben.
- Öffne den Pull Request mit `scripts/create-issue-pr.sh`; das Script übernimmt
  Project, Milestone und Assignees aus dem Issue.
- Ein vollständiger Pull Request enthält `Closes #<nummer>`, eine
  Teilumsetzung eine nicht schließende Verknüpfung.
- CI und Review sind Voraussetzung für den Merge.
