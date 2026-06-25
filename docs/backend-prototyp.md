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
- `server/app.py` stellt JSON-Endpunkte bereit und enthält keine fachlichen SQL-Abfragen.
- `db/seed_demo.sql` überführt die Demo-Daten aus dem Prototyp in relationale Tabellen.

## Start

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m server.app --init --seed --reset
```

Danach läuft der Server standardmäßig unter:

```text
http://127.0.0.1:8000
```

## Aktuelle Endpunkte

- `GET /api/health`
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
- `GET /api/round-summary?round_id=1`

Die REST-Schicht arbeitet gegen Repositories und Ressourcen-Metadaten. Neue Ressourcen sollten daher zuerst in `server/models.py` als SQLAlchemy-Modell und `Resource` beschrieben und dann in `server/repositories.py` fachlich ergänzt werden.

`POST /api/planning-settings` arbeitet als Upsert je `exam_round_id`. Die Repository-Schicht prüft dabei, ob bearbeitendes Mitglied und Standardort zur Prüfungsrunde gehören. Änderungen an `max_exam_days_per_week` sind nur für Mitglieder mit der Rolle `chair` erlaubt.

`POST /api/member-availabilities` arbeitet als Upsert je Kombination aus Prüfungsrunde, Ausschussmitglied und möglichem Prüfungstag. Die Repository-Schicht prüft die Rundenzugehörigkeit und setzt `responded_at` automatisch, sobald die Verfügbarkeit nicht mehr `pending` ist. Bei `pending` wird `responded_at` wieder geleert.

## Nächste Ausbaustufe

Als nächstes sollten Planungsvorschläge und weitere Service-Regeln entstehen. Die Regeln, die im Schema bewusst nicht als Datenbank-Constraints modelliert sind, gehören in Service-Funktionen:

- MEPs nur am Tagesende
- kein reiner MEP-Prüfungstag
- mindestens drei Prüfer je Tagesabschnitt
- alle Vertreterseiten je Tagesabschnitt abgedeckt
- Fallback nicht zugleich regulärer Prüfer
- nur Vorsitzender darf `max_exam_days_per_week` ändern
