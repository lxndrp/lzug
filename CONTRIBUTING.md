# Zu lzug beitragen

Danke für Beiträge zu `lzug`. Dieses Dokument beschreibt die lokale
Entwicklung; fachliche Prioritäten und Akzeptanzkriterien bleiben in GitHub
Issues und im Project [lzug Roadmap](https://github.com/users/lxndrp/projects/2).

## Voraussetzungen und Einrichtung

Die projektweit festgelegten Werkzeuge werden von [mise](https://mise.jdx.dev/)
verwaltet. Zusätzlich wird [uv](https://docs.astral.sh/uv/) benötigt. Nach der
Installation beider Werkzeuge:

```sh
mise install
mise run setup
```

`mise run setup` erstellt die Python-Umgebung aus `uv.lock` und installiert die
Frontend-Abhängigkeiten mit npm. Das Projekt verwendet npm und
`frontend/package-lock.json`; pnpm wird nicht verwendet.

## Lokal entwickeln

Den Backend-Server mit Demo-Daten starten:

```sh
.venv/bin/python -m backend.app --init --seed --reset
```

Die JSON-API läuft dann unter `http://127.0.0.1:8000/api/`. Ihre verbindliche
Beschreibung ist unter `http://127.0.0.1:8000/api/openapi.json` verfügbar,
Swagger UI unter `http://127.0.0.1:8000/api/docs`.

In einem zweiten Terminal das Angular-Frontend starten:

```sh
cd frontend
npm start
```

Es ist unter `http://localhost:4200/` erreichbar und leitet `/api` über den
lokalen Proxy an das Backend weiter.

## Qualität und Dokumentation

Vor einem Pull Request die betroffenen Prüfungen und anschließend den
vollständigen Lauf ausführen:

```sh
mise quality
```

Der Lauf enthält Backend-Linting, Formatierung, Sicherheitsprüfung, Tests und
Coverage, Frontend-Linting, Produktionsbuild und Tests sowie Browser- und
Accessibility-Prüfungen. Die vollständige Dokumentation mit Python- und
TypeScript-Referenzen entsteht mit `mise run docs`.

Frontend-spezifische Befehle und die E2E-Isolation beschreibt
[frontend/README.md](frontend/README.md). Architektur, API-Vertrag,
Dokumentationsstandard und der vollständige [Arbeitsprozess](docs/developers/arbeitsprozess.md)
stehen im [Entwicklerhandbuch](docs/developers/index.md).

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
