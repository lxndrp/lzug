# Datenbankschema

Die aktuelle, ausführbare Schema-Referenz ist `db/schema.sql` im Repository. Sie und die versionierten Migrationen unter `db/migrations/` sind maßgeblich für den tatsächlichen Datenbankstand.

Das aktuelle Backend verwendet SQLite lokal und SQLAlchemy. Primärschlüssel,
Enums, Zeitstempel und Booleans sind SQLite-kompatibel modelliert; mehrzeilige
fachliche Regeln werden in Repositories und Services validiert. Die Entscheidung einschließlich des später möglichen PostgreSQL-Pfads hält [ADR-0001](decisions/0001-lokale-relationale-persistenz.md) fest.

Diese Referenz ersetzt weder `db/schema.sql` noch die Migrationen.

## Betriebskonfiguration

Die Anwendung verwendet standardmäßig `/data/lzug.sqlite`. Ein anderer
Dateipfad kann mit `--db` oder `LZUG_DATABASE_PATH` gesetzt werden; alternativ
akzeptieren `--database-url` und `LZUG_DATABASE_URL` eine Datei-URL wie
`sqlite:////data/lzug.sqlite`. URL und Pfad dürfen nicht gleichzeitig gesetzt
werden. `:memory:` und SQLite-URLs mit Query-Parametern sind für den
Self-Hosting-Prozess nicht vorgesehen.

Beim Öffnen jeder Verbindung werden `PRAGMA foreign_keys = ON`,
`PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL` und
`PRAGMA busy_timeout = 5000` gesetzt. Dadurch bleiben Fremdschlüssel auch bei
neuen Verbindungen aktiv, Leser können während eines Schreibers weiterarbeiten
und kurzfristige konkurrierende Schreibzugriffe warten. WAL erzeugt neben der
Datenbank temporäre `-wal`- und `-shm`-Dateien; das persistente Datenverzeichnis
muss deshalb neben `lzug.sqlite` auch diese Laufzeitdateien zulassen.

`--init` initialisiert das Schema und führt den vorhandenen Schema-Lebenszyklus
aus. Ohne bereite Datenbank beendet sich der Backend-Start mit einem Fehler.
Der Healthcheck prüft dieselben Voraussetzungen und liefert bei fehlender
Readiness HTTP 503. Sicherung, Wiederherstellung und Rollback bleiben dem
nachgelagerten Betriebsumfang aus #117 vorbehalten.

## Dokumentmetadaten

Die Tabelle `document` enthält die interne `storage_id`, den geprüften
Anzeigenamen, Medientyp, Größe und SHA-256-Prüfsumme. Die `storage_id` wird
serverseitig erzeugt und darf nicht aus einem Benutzerpfad stammen. Der
Dateiinhalt liegt getrennt unter `/data/documents`; die Datenbank enthält keine
unkontrollierten Dateisystempfade. Backup- und Restore-Funktionen bleiben
außerhalb von #118.
