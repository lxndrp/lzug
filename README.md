# lzug

[![CI](https://github.com/lxndrp/lzug/actions/workflows/ci.yml/badge.svg)](https://github.com/lxndrp/lzug/actions/workflows/ci.yml)
![Status](https://img.shields.io/badge/status-prototype-yellow)
![Coverage](https://img.shields.io/badge/coverage-83%25-brightgreen)

`lzug` ist eine Web-App zur Unterstützung eines IHK-Prüfungsausschusses bei der Organisation halbjährlicher Fachinformatiker-Prüfungen.

Der aktuelle Fokus liegt auf der Prüfungsrunde:

- Verwaltung von Prüflingen
- Import von Prüflingsdaten
- Pflege von Ausschussmitgliedern und Prüfungsorten
- Terminfindung mit Verfügbarkeiten
- automatisierter Planungsvorschlag
- MEP- und Prüfungsversuchslogik
- Vorbereitung eines persistenten Server-Datenmodells

## Projektstruktur

```text
lzug/
├── db/
│   ├── schema.sql
│   └── seed_demo.sql
├── docs/
│   ├── datenmodell.md
│   ├── relationales-schema.md
│   └── backend-prototyp.md
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

Die technische Einordnung des ersten Backends ist dokumentiert in:

```text
docs/backend-prototyp.md
```

Ein erster persistenter Backend-Prototyp nutzt SQLite über SQLAlchemy. Die Abhängigkeiten sind in `pyproject.toml` beschrieben:

Voraussetzung fuer Backend und Frontend sind Python 3.14.6 und Node.js 26.5.0, die über **mise** verwaltet werden (mit Fallback auf pyenv/nvm-kompatible Versionsdateien).

### Umgebung einrichten

**Installation (alle Plattformen):**

Installiere [mise](https://mise.jdx.dev/):

```bash
brew install mise
```

Dann installiere die in `.python-version` und `.node-version` definierten Versionen:

```bash
mise install
```

Dies installiert automatisch Python 3.14.6 und Node.js 26.5.0 und erstellt automatisch ein Virtual Environment unter `.venv`.

**Abhängigkeiten installieren:**

```bash
mise run setup
```

Dies installiert automatisch:
- Python-Abhängigkeiten: `pip install -e ".[dev]"`
- Frontend-Abhängigkeiten: `npm install`

Oder manuell:

```bash
.venv/bin/python -m pip install -e ".[dev]"
cd frontend && npm install
```
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

Danach stehen JSON-Endpunkte unter `http://127.0.0.1:8000/api/` bereit, z. B.:

```text
/api/health
/api/openapi.json
/api/docs
/api/round-summary?round_id=1
/api/planning-proposals
/api/exam-rounds/1/confirm-plan
/api/candidates
/api/candidates/1
/api/members
/api/locations
/api/planning-settings?round_id=1
/api/candidate-exam-days?round_id=1
/api/member-availabilities?round_id=1
/api/exam-days?round_id=1
/api/exam-slots
/api/exam-day-assignments
```

Für die Kernressourcen `committees`, `members`, `locations`, `exam-rounds` und `candidates` sind die CRUD-Muster `GET`, `POST`, `PATCH` und `DELETE` vorbereitet. Planungsparameter und Verfügbarkeiten sind ebenfalls schreibbar; `POST /api/planning-settings` und `POST /api/member-availabilities` aktualisieren vorhandene Einträge für dieselbe Prüfungsrunde bzw. dieselbe Mitglied/Tag-Kombination.

`POST /api/planning-proposals` erzeugt einen deterministischen Planungsvorschlag für eine Prüfungsrunde, persistiert Prüfungstage, Slots und Besetzungen und setzt die Runde auf `plan_proposed`. MEP-Slots werden am Tagesende platziert; der Response enthält einen Validierungsreport.

`POST /api/exam-rounds/{id}/confirm-plan` bestätigt einen vorhandenen Planungsvorschlag, setzt Prüfungstage und Slots auf `confirmed` und überführt die Runde nach `plan_confirmed`. Bestätigte Planungstage können nicht mehr durch einen neuen Vorschlag ersetzt werden.

Die API ist selbstbeschreibend:

- `GET /api` liefert den Einstiegspunkt mit Links auf Ressourcen, Healthcheck, OpenAPI und Docs.
- `GET /api/openapi.json` liefert eine OpenAPI-3.1-Spezifikation.
- `GET /api/docs` liefert eine Swagger-UI-Ansicht auf Basis von `/api/openapi.json`.
- JSON-Antworten enthalten HAL-nahe `_links` mit `self`, `collection` und erlaubten Operationen.
- Listen werden als `{ "items": [...], "_links": {...} }` ausgeliefert.

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

In VS Code stehen dafuer die Tasks `Tests mit Coverage`, `Coverage XML erzeugen`, `Coverage HTML erzeugen`, `Frontend Tests`, `Frontend Coverage`, `Frontend Build`, `Alle Tests` und `Alle Coverage Reports` bereit. Die empfohlene Erweiterung Coverage Gutters nutzt `coverage.xml` und `frontend/coverage/frontend/lcov.info` direkt im Editor.

Wenn Node.js installiert ist, prüft der Harness zusätzlich `app.js` mit `node --check`; ohne Node wird nur dieser optionale Syntaxcheck übersprungen.

## Nächster geplanter Schritt

Der nächste sinnvolle Schritt ist, die erzeugte und bestätigte Planung im Frontend zu nutzen und danach Benachrichtigungs- sowie Kalenderereignisse anzubinden.
