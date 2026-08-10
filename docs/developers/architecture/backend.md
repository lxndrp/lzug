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
für neue Datenbanken. Migrationen unter `db/migrations/` werden mit `--init` in
numerischer Reihenfolge genau einmal ausgeführt und in `schema_migration`
protokolliert. Die zugehörigen SHA-256-Prüfsummen stehen in
`schema_migration_checksum`; unbekannte, lückenhafte oder manipulierte Stände
werden abgewiesen. Ein bestehender SQLite-Bestand ohne versionierte Historie
wird nicht heuristisch übernommen.

Vor einer ausstehenden Migration erzeugt der Start einen SQLite-Sicherheitssnapshot
unter `/data/backups` beziehungsweise im konfigurierten Backup-Pfad. Das ist
eine migrationsbezogene Schutzkopie und keine allgemeine Backup-, Restore- oder
Exportfunktion. Migrationen werden über eine neben der Datenbank liegende
Dateisperre serialisiert; der zweite Start wartet und prüft danach den bereits
aktualisierten Stand erneut.

Jede SQLAlchemy-Verbindung aktiviert Foreign Keys, WAL, `synchronous=NORMAL`
und einen `busy_timeout` von fünf Sekunden. WAL erlaubt parallele Leser und
serialisiert weiterhin Schreibzugriffe; ein kurzfristig belegter Schreibzugriff
wird innerhalb dieses Timeouts abgewartet. Bleibt die Datenbank danach gesperrt,
antwortet die API mit HTTP 503 und der Request kann wiederholt werden. Die
Transaktionsgrenze bleibt `session_scope`: erfolgreiche fachlich zusammenhängende
Änderungen werden gemeinsam committed, Fehler gemeinsam zurückgerollt.

Der Start prüft nach optionaler Initialisierung die Erreichbarkeit, das Schema,
die Migrationshistorie und die effektiven SQLite-Einstellungen. `GET
/api/health` liefert bei bereiter Datenbank HTTP 200, sonst HTTP 503. Die
Antwort enthält den sicheren Grund sowie aktuellen, Ziel- und ausstehenden
Migrationsstand und die Historie; Fachdaten oder Verbindungsgeheimnisse werden
nicht ausgegeben. Die API startet bei einem ungeeigneten Schema nicht. Vor dem
Start prüft das Backend außerdem die Existenz beziehungsweise Anlegbarkeit von
`/data`, `/data/documents` und `/data/backups`, Schreibzugriff und den
prüfbaren freien Speicher. Für lokale Tests können `LZUG_DATA_DIR`,
`LZUG_DOCUMENTS_PATH` und `LZUG_BACKUPS_PATH` oder die entsprechenden
CLI-Optionen `--data-dir`, `--documents` und `--backups` diese Pfade
überschreiben; der Self-Hosting-Standard bleibt unter `/data`.

Fachliche Änderungen werden weiterhin ausschließlich über SQLAlchemy-Sessions
und Repositories committed. Jede Migration besitzt ihre eigene SQL-Transaktion;
erst nach erfolgreichem Commit wird der Historieneintrag geschrieben. Bei einem
Fehler wird der Eintrag nicht vorgetäuscht und der Start bleibt geschlossen.
SQLite kann bereits committed Migrationen nicht durch einen späteren Prozess
automatisch zurückrollen; die Schutzkopie muss für eine Wiederherstellung
manuell beziehungsweise durch den späteren Betriebsumfang verwendet werden.

Dokumente werden über `backend.document_storage.DocumentStorage` gespeichert.
Der lokale Adapter verwendet zufällige interne 32-stellige Hexadezimal-IDs und
veröffentlicht Dateien atomar ohne Überschreiben. Der ursprüngliche Dateiname
bleibt reine Metadaten und wird auf Pfad- und Steuerzeichen geprüft.
`DocumentService` hält Dateiinhalt und SQLAlchemy-Metadaten mit Kompensation
bei einem fehlgeschlagenen Gegenschritt zusammen. Ein S3-Adapter ist lediglich
durch diese kleine Schnittstelle vorbereitet und nicht Teil der
Erstveröffentlichung.

Gesetzliche Feiertage werden bundes- und landesweit berücksichtigt. Gemeindespezifische Regeln leitet die Anwendung nicht aus einer reinen Bundeslandauswahl ab.
