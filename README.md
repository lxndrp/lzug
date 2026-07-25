# lzug

[![CI](https://github.com/lxndrp/lzug/actions/workflows/ci.yml/badge.svg)](https://github.com/lxndrp/lzug/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-prototype-yellow)
![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen)

`lzug` ist eine Web-App zur Unterstützung eines IHK-Prüfungsausschusses bei der Organisation halbjährlicher Fachinformatiker-Prüfungen. Die App richtet sich an die Ausschussarbeit, nicht an interne IHK-Sachbearbeitung.

Fachlich gliedert sich das Produkt in zwei zentrale Bereiche:

- **Prüfungen planen**: Prüflinge, Ausschussmitglieder, Orte, Verfügbarkeiten, Planungsvorschlag, Bestätigung, Ausfallprozess und Terminbereitstellung.
- **Prüfungen durchführen**: Tagesansicht, Anwesenheiten, Prüfungsstatus, Protokollierung, Ergebnis-/Abschlussdaten und Abschlusslogik. Dieser Bereich ist noch fachlich zu schärfen.

Der aktuelle Entwicklungsstand liegt vor allem im Bereich **Prüfungen planen**:

- Verwaltung von Prüflingen
- Import von Prüflingsdaten
- Pflege von Ausschussmitgliedern und Prüfungsorten
- Terminfindung mit Verfügbarkeiten
- automatisierter Planungsvorschlag
- MEP- und Prüfungsversuchslogik
- Vorbereitung eines persistenten Server-Datenmodells

Der fachliche Referenzstand mit umgesetzten und offenen Anforderungen steht in:

```text
ROADMAP.md
```

Die operative Planung wird im GitHub Project [lzug Roadmap](https://github.com/users/lxndrp/projects/2) geführt.

## Projektstruktur

```text
lzug/
├── db/
│   ├── schema.sql
│   └── seed_demo.sql
├── docs/
│   ├── ARCHITECTURE.md
│   ├── datenmodell.md
│   ├── relationales-schema.md
│   └── backend-prototyp.md
├── ROADMAP.md
├── frontend/
│   └── Angular-App für die produktivere Oberfläche
├── backend/
│   ├── app.py
│   ├── database.py
│   ├── models.py
│   ├── repositories.py
│   └── store.py
└── prototypes/
    └── pruefungsrunde-prototyp/
        ├── index.html
        ├── app.js
        ├── styles.css
        └── README.md
```

## Aktueller Stand

Der klickbare Prototyp ist eine statische Web-App ohne Build-Schritt. Er kann lokal direkt im Browser geöffnet werden:

```text
prototypes/pruefungsrunde-prototyp/index.html
```

Das fachliche Datenmodell befindet sich in:

```text
docs/datenmodell.md
```

Das relationale Basisschema befindet sich in:

```text
db/schema.sql
```

Die technische Architektur befindet sich in:

```text
docs/ARCHITECTURE.md
```

Der fachliche Roadmap- und Anforderungsstand befindet sich in:

```text
ROADMAP.md
```

Die historische technische Einordnung des ersten Backend-Prototyps ist dokumentiert in:

```text
docs/backend-prototyp.md
```

Die aktuelle technische Architektur, API-Struktur, Backend-/Frontend-Schichtung und CI-Einordnung stehen in `docs/ARCHITECTURE.md`.

### Technischer Kurzüberblick

Die Entwicklungsumgebung ist im Repository festgelegt und wird mit **mise** verwaltet:

- Python `3.14.6` fuer das Backend
- `holidays` als kuratierte Feiertagsberechnung im Python-Backend
- Node.js `26.5.0` und npm fuer das Frontend
- uv fuer die Python-Umgebung und das Lockfile `uv.lock`
- Angular `22`, TypeScript `6` und Taiga UI im Verzeichnis `frontend/`
- npm mit `frontend/package-lock.json`; pnpm wird nicht verwendet

Weitere technische Details stehen in `docs/ARCHITECTURE.md`.

Frontend-spezifische Kurzkommandos stehen zusätzlich in:

```text
frontend/README.md
```

### Umgebung einrichten

**macOS-Installation:**

Installiere [mise](https://mise.jdx.dev/) und [UV](https://docs.astral.sh/uv/):

```bash
brew install mise uv
```

Das Homebrew-Beispiel ist ein macOS-spezifischer Einstieg. Für Linux, Windows
und alternative Installationswege bitte die offiziellen Installationshinweise
von `mise` und `uv` verwenden.

Hinweis zu Intel-Macs: Das vorliegende Projekt wurde auch auf einem Intel-Mac
mit extern installiertem `mise`, `uv`, Python und Node.js genutzt. Der
`mise`-interne Homebrew-/Bootstrap-Paketmanager unterstützt Intel-Macs jedoch
nicht offiziell; projektbezogene Systempakete sollten dort nicht über
`mise bootstrap packages` erwartet werden.

Dann installiere die in `.python-version` und `.node-version` definierten Versionen:

```bash
mise install
```

Dies installiert automatisch Python 3.14.6 und Node.js 26.5.0.

**Abhängigkeiten installieren:**

```bash
mise run setup
```

Dies erstellt automatisch:
- `.venv` Virtual Environment (via `uv venv --python "$(mise which python)" --clear --seed`)
- Python-Abhängigkeiten aus Lockfile (via `uv sync --locked --extra dev`)
- Frontend-Abhängigkeiten (via `npm install`)

Oder manuell:

```bash
uv venv --python "$(mise which python)" --clear --seed
uv sync --locked --extra dev
cd frontend && npm install
```

Der Server startet danach mit:

```bash
.venv/bin/python -m backend.app --init --seed --reset
```

Die Angular-App liegt unter `frontend/` und nutzt im Entwicklungsmodus einen Proxy auf den Python-Server:

```bash
cd frontend && npm start
```

Der Python-Server sollte dafür parallel unter `http://127.0.0.1:8000` laufen.

Danach stehen JSON-Endpunkte unter `http://127.0.0.1:8000/api/` bereit. Die API ist selbstbeschreibend:

```text
http://127.0.0.1:8000/api
http://127.0.0.1:8000/api/openapi.json
http://127.0.0.1:8000/api/docs
```

Die API-Struktur, Ressourcen und Planungsaktionen sind in `docs/ARCHITECTURE.md` beschrieben.

## Tests

Der Test-Harness nutzt `unittest` und die in `pyproject.toml` beschriebenen Projektabhängigkeiten. Er deckt die aktuellen Applikationsteile ab:

- Datenbankschema, Seed-Daten und Kern-Constraints
- Repository-Funktionen und Rundenzusammenfassung
- deterministische Planungsvorschläge mit Slots, Besetzungen und MEP-Regeln
- Bestätigungsworkflow für vorgeschlagene Prüfungspläne
- Angular-Frontend-Schale mit API-Anbindung an Rundenzusammenfassung und Planungsaktionen
- JSON-API über den echten HTTP-Handler ohne lokalen Port
- OpenAPI-, Docs- und HATEOAS-Kontrakte
- statischen Prototyp mit Asset-, Navigations- und JavaScript-Syntaxprüfung

Alle Tests laufen mit:

```bash
.venv/bin/python -m unittest
cd frontend && npm run test:ci
```

Backend- und Frontend-Tests koennen auch einzeln ausgefuehrt werden:

```bash
.venv/bin/python -m unittest
cd frontend && npm run test:ci
```

Falls Chrome nicht im Standardpfad liegt, muss `CHROME_BIN` auf die Chrome-Binary zeigen.

Coverage ist als Dev-Extra konfiguriert:

```bash
.venv/bin/python -m coverage run -m unittest
.venv/bin/python -m coverage report
.venv/bin/python -m coverage xml
cd frontend && npm run test:coverage
```

Der vollständige lokale QS-Lauf prüft Formatierung, Linting, Backend- und
Frontend-Coverage, Dependency-Sicherheit, Produktionsbuild sowie Browser- und
Accessibility-Tests:

```bash
mise run quality
```

Die versionierte Entwicklerdokumentation mit Python- und TypeScript-Referenz
wird lokal erzeugt mit:

```bash
mise run docs
```

Das Ergebnis liegt unter `site/`. Es wird in CI nur als geschütztes Artefakt
bereitgestellt; eine öffentliche Dokumentationsseite ist nicht aktiviert.

Für die Browser-Tests wird Playwright verwendet. Der Lauf startet Backend und
Frontend automatisch und verwendet eine isolierte SQLite-Testdatenbank. Der
Frontend-Coverage-Gate liegt aktuell bei mindestens 70 Prozent Statements und
Lines, 65 Prozent Functions sowie 45 Prozent Branches.

In VS Code stehen dafuer Tasks fuer Backend- und Frontend-Tests, Coverage,
Browser-E2E, Security, statische Checks und den kompletten QS-Lauf bereit. Die
empfohlene Erweiterung Coverage Gutters nutzt `coverage.xml` und
`frontend/coverage/frontend/lcov.info` direkt im Editor.

Der npm-Sicherheitscheck ist dabei bewusst ein separates, risikobasiertes
Critical-Gate für produktive Abhängigkeiten. Die verbindliche Triage-Fristen,
Ausnahmen für transitive Befunde und Dependabot-Konfiguration stehen in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#npm-sicherheitsgate-und-dependabot-triage).

Wenn Node.js installiert ist, prüft der Harness zusätzlich `app.js` mit `node --check`; ohne Node wird nur dieser optionale Syntaxcheck übersprungen.

## Roadmap

Die fachliche Roadmap wird in `ROADMAP.md` dokumentiert und operativ im GitHub Project [lzug Roadmap](https://github.com/users/lxndrp/projects/2) nachverfolgt.
