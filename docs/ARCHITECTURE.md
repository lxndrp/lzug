# Architektur

Stand: 16.07.2026

Dieses Dokument beschreibt die technische Architektur von `lzug`. Fachlicher Umfang und Roadmap stehen in `../ROADMAP.md`; Arbeitsregeln fuer Codex und andere Agents stehen in `../AGENTS.md`.

## Überblick

`lzug` besteht aktuell aus vier wesentlichen Teilen:

- **Angular-Frontend** in `frontend/`
- **Python-Backend** in `backend/`
- **Relationales Datenmodell** in `db/schema.sql` und SQLAlchemy-Modellen
- **Statischer Prototyp** in `prototypes/pruefungsrunde-prototyp/`

Die produktive Weiterentwicklung findet in Frontend und Backend statt. Der statische Prototyp bleibt fachliche und UX-bezogene Referenz.

## Technologieentscheidungen

### Runtime und Toolchain

- Python `3.14.6` fuer Backend und Tests
- Node.js `26.5.0` und npm fuer das Frontend
- `mise` fuer projektweite Runtime-Versionen und Tasks
- `uv` fuer Python-Umgebung, Dependency-Auflösung und `uv.lock`
- npm mit `frontend/package-lock.json`; pnpm wird nicht verwendet

`mise` selbst ist plattformuebergreifend dokumentiert. Das Homebrew-Beispiel in
der README ist macOS-spezifisch. Der `mise`-interne
Homebrew-/Bootstrap-Paketmanager unterstuetzt Intel-Macs nicht offiziell; auf
Intel-Macs sollte das Projekt mit extern installierten Werkzeugen bzw. den
normalen `mise`-Tool-Versionen betrieben werden.

Die Versionspins liegen in:

- `.mise.toml`
- `.python-version`
- `.node-version`
- `uv.lock`
- `frontend/package-lock.json`

### Backend

Das Backend ist ein Python-Paket unter `backend/`.

Wichtige Module:

- `backend/app.py`: HTTP-Handler auf Basis von `BaseHTTPRequestHandler` und `ThreadingHTTPServer`
- `backend/database.py`: SQLAlchemy-Engine, Session-Kontext und Datenbankinitialisierung
- `backend/models.py`: SQLAlchemy-ORM-Modelle und REST-Ressourcen-Metadaten
- `backend/repositories.py`: fachnahe CRUD- und Leseoperationen
- `backend/store.py`: generischer SQLAlchemy-basierter CRUD-Adapter
- `backend/planning.py`: Planungsvorschlag, Slot-Erzeugung und Planbestätigung
- `backend/hateoas.py`: HAL-nahe Links in JSON-Antworten
- `backend/openapi.py`: OpenAPI-3.1-Spezifikation

Der Anwendungscode soll keine fachlichen SQL-Statements enthalten. Persistenz laeuft ueber SQLAlchemy-Modelle, Repositories und REST-nahe Ressourcen.

### Frontend

Das Frontend liegt unter `frontend/` und nutzt:

- Angular `22`
- TypeScript `6`
- CoreUI fuer Oberflaechenkomponenten
- Angular Router fuer die Hauptansichten
- einen API-Service fuer die Kommunikation mit dem Backend

Wichtige Bereiche:

- `frontend/src/app/api/`: API-Modelle, API-Service und Rundenauswahl-Kontext
- `frontend/src/app/dashboard/`: Dashboard
- `frontend/src/app/candidates/`: Prüflinge
- `frontend/src/app/committee/`: Ausschussmitglieder
- `frontend/src/app/locations/`: Prüfungsorte
- `frontend/src/app/planning/`: Verfügbarkeiten, Planungsparameter, Vorschlag und Bestätigung

Im Entwicklungsmodus nutzt Angular einen Proxy auf den Python-Server unter `http://127.0.0.1:8000`.

Wichtige Frontend-Konfiguration:

- `frontend/angular.json`: Angular-Build, Dev-Server, Test-Builder und Produktionsbudgets
- `frontend/proxy.conf.json`: Proxy von `/api` auf `http://127.0.0.1:8000`
- `frontend/karma.conf.cjs`: Karma/Jasmine, Chrome-Launcher und Coverage-Gates
- `frontend/playwright.config.ts`: E2E-Webserver, Testdatenbank, Browser-Konfiguration und Artefakte
- `frontend/eslint.config.js`: ESLint-Regeln fuer TypeScript und Prettier-Integration
- `frontend/THIRD_PARTY_NOTICES.md`: Lizenzhinweise fuer Frontend-Abhaengigkeiten

### Datenbank

Der aktuelle Stand nutzt SQLite lokal und SQLAlchemy im Backend. Das relationale Basisschema liegt in:

```text
db/schema.sql
```

Die fachliche Einordnung des Schemas steht in:

```text
docs/relationales-schema.md
```

Das Schema ist PostgreSQL-nah angelegt, aber SQLite-kompatibel. Fachliche Mehrzeilenregeln werden nicht vollständig durch Datenbankconstraints erzwungen, sondern in Repository- und Service-Logik validiert.

## Backend-Schichten

```text
HTTP Handler
  -> HATEOAS/OpenAPI/JSON-Erzeugung
  -> ResourceRepository / PlanningService
  -> SQLAlchemy Models / Store
  -> SQLite-Datenbank
```

### HTTP-Schicht

`backend/app.py` stellt die JSON-API bereit. Die HTTP-Schicht:

- parst Pfade, Query-Parameter und JSON-Payloads
- routet generische Ressourcen auf `ResourceRepository`
- routet Planungsaktionen auf `PlanningService`
- wandelt Fehler in HTTP-Statuscodes um
- liefert HAL-nahe `_links`

### Repository-Schicht

`ResourceRepository` bündelt fachnahe Lese- und Schreiboperationen. Neue REST-Ressourcen sollen zuerst als SQLAlchemy-Modell und `Resource` in `backend/models.py` beschrieben und danach in `backend/repositories.py` fachlich ergänzt werden.

Spezielle Repository-Operationen existieren aktuell unter anderem fuer:

- Prüflinge
- Planungsparameter
- Verfügbarkeiten
- Rundenzusammenfassung

### Planungsservice

`PlanningService` erzeugt und bestätigt Planungsvorschläge.

Aktuelle Regeln:

- reguläre Prüfungen werden zuerst geplant
- MEP-Slots werden am Tagesende platziert
- ein Prüfungstag besteht nie ausschließlich aus MEP-Slots
- je Tagesabschnitt werden Arbeitgeber-, Arbeitnehmer- und Schulvertretung sowie ein Fallback berücksichtigt
- bestätigte Pläne blockieren das Ersetzen durch neue Vorschläge

## API

Die API ist selbstbeschreibend:

- `GET /api` liefert Einstiegspunkte
- `GET /api/health` liefert den Healthcheck
- `GET /api/openapi.json` liefert die OpenAPI-3.1-Spezifikation
- `GET /api/docs` liefert Swagger UI

Kernressourcen nutzen REST-nahe CRUD-Muster mit `GET`, `POST`, `PATCH` und `DELETE`.

Aktuelle Ressourcen und Aktionen:

- `committees`
- `members`
- `locations`
- `exam-rounds`
- `candidates`
- `planning-settings`
- `candidate-exam-days`
- `member-availabilities`
- `exam-days`
- `exam-slots`
- `exam-day-assignments`
- `round-summary`
- `planning-proposals`
- `exam-rounds/{id}/confirm-plan`

JSON-Antworten enthalten HAL-nahe `_links` mit `self`, `collection` und erlaubten Operationen. Listen werden als Objekt mit `items` und `_links` ausgeliefert.

## Frontend-Integration

Das Frontend konsumiert die JSON-API über `PlanningApiService`. Der `RoundContextService` hält den aktuell betrachteten Prüfungsdurchgang.

Die Angular-App ist nach fachlichen Ansichten gegliedert:

- Dashboard
- Prüflinge
- Ausschuss
- Prüfungsorte
- Planung

Die Anwendung ist kein Marketing- oder Landingpage-Projekt, sondern ein Arbeitswerkzeug für wiederkehrende Ausschussprozesse.

## Tests und Qualität

Die technische Qualitätssicherung ist mehrschichtig:

- Backend: `unittest`, Coverage, Ruff, Black, `pip-audit`
- Frontend: Karma/Jasmine, Angular Build, ESLint, Prettier, npm audit
- Browser: Playwright E2E und Accessibility-Prüfungen mit axe
- CI: GitHub Actions mit getrennten Jobs für Backend, Frontend und Browser-E2E

Die vollständige lokale Prüfung läuft über:

```sh
mise run quality
```

Frontend-Coverage-Gates:

- Statements: 70 Prozent
- Lines: 70 Prozent
- Functions: 65 Prozent
- Branches: 45 Prozent

Playwright startet fuer E2E- und Accessibility-Tests automatisch:

- Backend unter `http://127.0.0.1:8000`
- Angular-Dev-Server unter `http://127.0.0.1:4200`
- isolierte SQLite-Testdatenbank unter `var/lzug-e2e.sqlite3`

Die vollständige CI-Konfiguration liegt in:

```text
.github/workflows/ci.yml
```

## Abhängigkeitspflege

Dependabot verwaltet Updates für:

- Python-/uv-Abhängigkeiten
- npm-Abhängigkeiten im Frontend
- GitHub Actions

Die Konfiguration liegt in:

```text
.github/dependabot.yml
```

Runtime-Pins wie Python- und Node-Versionen bleiben bewusste Projektentscheidungen und werden bei neuen Runtime-Releases manuell bewertet.

## Migration und Ausbau

### PostgreSQL

SQLite ist die lokale Entwicklungsdatenbank. Ein späterer Wechsel auf PostgreSQL bleibt vorbereitet, weil die laufenden Repository-Operationen nicht an SQLite-spezifische APIs gebunden sind.

Mögliche Schritte:

- `INTEGER PRIMARY KEY` durch UUIDs ersetzen
- `TEXT`-Zeitstempel durch `TIMESTAMPTZ` ersetzen
- Boolean-Spalten auf `BOOLEAN` umstellen
- Text-Enums optional durch PostgreSQL-Enums oder Lookup-Tabellen ersetzen
- zusätzliche Constraints für überlappende Slots prüfen

### Offene Architekturthemen

- produktives Authentifizierungs- und Rollenmodell
- Importpipeline für Prüflinge
- Ausfallprozess mit Benachrichtigungen und Eskalationen
- Kalenderintegration
- Datenmodell und API für das Epic `Prüfungen durchführen`
- Migrationen statt reinem Basisschema
