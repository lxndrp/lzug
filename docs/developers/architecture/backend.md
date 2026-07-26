# Backend und Datenzugriff

Das Backend ist ein Python-Paket. `backend/app.py` stellt die HTTP-Schnittstelle auf Basis von `BaseHTTPRequestHandler` und `ThreadingHTTPServer` bereit. Es parst Requests, routet Ressourcen und Planungsaktionen, übersetzt Fehler in HTTP-Statuscodes und erzeugt JSON mit HAL-nahen `_links`.

Die fachliche Verarbeitung liegt hinter der HTTP-Schicht:

- `backend/models.py` enthält SQLAlchemy-Modelle und Ressourcen-Metadaten.
- `backend/repositories.py` bündelt fachnahe Lese- und Schreiboperationen.
- `backend/store.py` ist der generische SQLAlchemy-basierte CRUD-Adapter.
- `backend/planning.py` erstellt und bestätigt Planungsvorschläge.
- `backend/candidate_days.py` berechnet mögliche Prüfungstage.
- `backend/holiday_provider.py` kapselt die Feiertagsberechnung mit `holidays`.

Anwendungscode enthält keine fachlichen SQL-Abfragen. Neue Ressourcen werden zuerst als SQLAlchemy-Modell und `Resource` beschrieben und danach fachlich ergänzt.

SQLite ist die lokale Entwicklungsdatenbank. `db/schema.sql` und `db/seed_demo.sql` sind die ausführbaren Quellen für Schema und Demo-Daten. Migrationen unter `db/migrations/` werden beim Start mit `--init` ausgeführt und in `schema_migration` protokolliert. Die Details stehen in der [Schema-Referenz](../database-schema.md).

Gesetzliche Feiertage werden bundes- und landesweit berücksichtigt. Gemeindespezifische Regeln leitet die Anwendung nicht aus einer reinen Bundeslandauswahl ab.
