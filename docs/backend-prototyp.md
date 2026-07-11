# lzug – erster Backend-Prototyp

Stand: 25.06.2026

## Entscheidung

Der Backend-Prototyp nutzt Python, SQLite und SQLAlchemy 2.x.

Gründe:

- SQLAlchemy kapselt Engine, Sessions und ORM-Mapping.
- Fach-/REST-Code arbeitet gegen Repositories und SQLAlchemy-Modelle statt gegen handgeschriebene SQL-Statements.
- SQLite bleibt als lokale Entwicklungsdatenbank nutzbar.
- `db/schema.sql` und `db/seed_demo.sql` bleiben die ausführbare Quelle für Schema und Demo-Daten.
- Der spätere Wechsel auf PostgreSQL wird leichter, weil die laufenden Repository-Operationen nicht mehr an SQLite-APIs hängen.

Das ist weiterhin bewusst noch kein endgültiger Web-Stack. Der Wert liegt darin, das relationale Modell ausführbar zu halten und die API-Oberfläche mit einer stabileren Persistenzabstraktion wachsen zu lassen.

## Dateien

- `pyproject.toml` beschreibt SQLAlchemy als Projektabhängigkeit.
- `server/database.py` kapselt SQLAlchemy-Engine, Session-Kontext und Initialisierung.
- `server/models.py` beschreibt die aktuell genutzten Tabellen als SQLAlchemy-ORM-Modelle und API-Ressourcen.
- `server/store.py` enthält einen kleinen SQLAlchemy-basierten CRUD-Adapter für generische Repository-Operationen.
- `server/repositories.py` bündelt fachnahe Lese- und Schreiboperationen.
- `server/planning.py` erzeugt deterministische Planungsvorschläge und persistiert Prüfungstage, Slots und Besetzungen.
- `server/hateoas.py` ergänzt JSON-Antworten um HAL-nahe `_links`.
- `server/openapi.py` erzeugt die OpenAPI-3.1-Spezifikation.
- `backend/app.py` stellt JSON-Endpunkte bereit und enthält keine fachlichen SQL-Abfragen.
- `db/seed_demo.sql` überführt die Demo-Daten aus dem Prototyp in relationale Tabellen.

## Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m backend.app --init --seed --reset
```

Danach läuft der Server standardmäßig unter:

```text
http://127.0.0.1:8000
```

## Aktuelle Endpunkte

- `GET /api`
- `GET /api/health`
- `GET /api/openapi.json`
- `GET /api/docs`
- `POST /api/planning-proposals`
- `POST /api/exam-rounds/{id}/confirm-plan`
- `GET /api/committees`
- `GET /api/committees/{id}`
- `POST /api/committees`
- `PATCH /api/committees/{id}`
- `DELETE /api/committees/{id}`
- dieselben CRUD-Muster für `members`, `locations`, `exam-rounds` und `candidates`
- `GET /api/planning-settings?round_id=1`
- `POST /api/planning-settings`
- `PATCH /api/planning-settings/{id}`
- `GET /api/candidate-exam-days?round_id=1`
- CRUD-Muster für `candidate-exam-days`
- `GET /api/member-availabilities?round_id=1`
- `POST /api/member-availabilities`
- `PATCH /api/member-availabilities/{id}`
- `GET /api/exam-days?round_id=1`
- `GET /api/exam-slots`
- `GET /api/exam-day-assignments`
- `GET /api/round-summary?round_id=1`

Die REST-Schicht arbeitet gegen Repositories und Ressourcen-Metadaten. Neue Ressourcen sollten daher zuerst in `server/models.py` als SQLAlchemy-Modell und `Resource` beschrieben und dann in `server/repositories.py` fachlich ergänzt werden.

Die API ist HAL-nah selbstbeschreibend. Einzelressourcen enthalten `_links.self`, `_links.collection` sowie Links für erlaubte Operationen wie `update` und `delete`. Listen werden als Objekt mit `items` und `_links` ausgeliefert, damit auch Sammlungen navigierbar sind. Die OpenAPI-Spezifikation liegt unter `/api/openapi.json`; `/api/docs` bindet Swagger UI gegen diese Spezifikation ein.

`POST /api/planning-settings` arbeitet als Upsert je `exam_round_id`. Die Repository-Schicht prüft dabei, ob bearbeitendes Mitglied und Standardort zur Prüfungsrunde gehören. Änderungen an `max_exam_days_per_week` sind nur für Mitglieder mit der Rolle `chair` erlaubt.

`POST /api/member-availabilities` arbeitet als Upsert je Kombination aus Prüfungsrunde, Ausschussmitglied und möglichem Prüfungstag. Die Repository-Schicht prüft die Rundenzugehörigkeit und setzt `responded_at` automatisch, sobald die Verfügbarkeit nicht mehr `pending` ist. Bei `pending` wird `responded_at` wieder geleert.

`POST /api/planning-proposals` erzeugt einen neuen Vorschlag für eine Prüfungsrunde. Vorhandene nicht bestätigte Vorschläge werden ersetzt. Der Service wählt je Tagesabschnitt mindestens drei reguläre Prüfer mit Arbeitgeber-, Arbeitnehmer- und Schulvertretung sowie einen zusätzlichen Fallback. Reguläre Prüfungen werden zuerst geplant; MEP-Slots werden am Tagesende platziert und niemals als einziger Slot eines Tages erzeugt. Der Response enthält persistierte Prüfungstage sowie einen Validierungsreport.

`POST /api/exam-rounds/{id}/confirm-plan` bestätigt einen vorgeschlagenen Plan. Dabei werden Prüfungstage und Slots auf `confirmed` gesetzt, Fallback-Besetzungen als bestätigt markiert und die Prüfungsrunde nach `plan_confirmed` überführt. Ein bestätigter Plan blockiert das Ersetzen durch einen neuen Vorschlag.

## Nächste Ausbaustufe

Als nächstes sollten die serverseitig erzeugten und bestätigten Planungsvorschläge im Frontend genutzt werden:

- Frontend-Anbindung der API für Planungsvorschlag, Prüfungstage, Slots und Besetzungen
- spätere Benachrichtigungs- und Kalenderereignisse
- Export- oder Kalenderansicht für bestätigte Termine
