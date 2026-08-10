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

SQLite ist die Datenbank für die einzelne Self-Hosting-Instanz. Der
Produktionsstandard ist `/data/lzug.sqlite` entsprechend
[ADR-0014](../decisions/0014-oci-einzelcontainer-und-persistentes-data.md);
der Pfad kann mit `--db`, `LZUG_DATABASE_PATH` oder einer SQLite-URL über
`--database-url` beziehungsweise `LZUG_DATABASE_URL` überschrieben werden.
Lokale Entwicklung kann beispielsweise `LZUG_DATABASE_PATH=var/lzug.sqlite3`
verwenden. `db/schema.sql` und `db/seed_demo.sql` sind die ausführbaren Quellen
für Schema und Demo-Daten. Migrationen unter `db/migrations/` werden beim Start
mit `--init` ausgeführt und in `schema_migration` protokolliert. Die Details
stehen in der [Schema-Referenz](../database-schema.md).

Jede SQLAlchemy-Verbindung aktiviert Foreign Keys, WAL, `synchronous=NORMAL`
und einen `busy_timeout` von fünf Sekunden. WAL erlaubt parallele Leser und
serialisiert weiterhin Schreibzugriffe; ein kurzfristig belegter Schreibzugriff
wird innerhalb dieses Timeouts abgewartet. Bleibt die Datenbank danach gesperrt,
antwortet die API mit HTTP 503 und der Request kann wiederholt werden. Die
Transaktionsgrenze bleibt `session_scope`: erfolgreiche fachlich zusammenhängende
Änderungen werden gemeinsam committed, Fehler gemeinsam zurückgerollt.

Der Start prüft nach optionaler Initialisierung die Erreichbarkeit, das Schema
und die effektiven SQLite-Einstellungen. `GET /api/health` liefert bei
bereiter Datenbank HTTP 200, sonst HTTP 503. Der Check ist eine Readiness-
Prüfung, kein Backup-, Migrations- oder Wiederherstellungsmechanismus.

Gesetzliche Feiertage werden bundes- und landesweit berücksichtigt. Gemeindespezifische Regeln leitet die Anwendung nicht aus einer reinen Bundeslandauswahl ab.
