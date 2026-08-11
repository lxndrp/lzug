# Datenbankschema

Die aktuelle, ausführbare Schema-Referenz ist `db/schema.sql` im Repository. Sie
und die versionierten Migrationen unter `db/migrations/` sind maßgeblich für
den tatsächlichen Datenbankstand. Der aktuelle Migrationsstand ist
`011_add_local_password_totp_auth.sql`.

Das aktuelle Backend verwendet SQLite lokal und SQLAlchemy. Primärschlüssel,
Enums, Zeitstempel und Booleans sind SQLite-kompatibel modelliert; mehrzeilige
fachliche Regeln werden in Repositories und Services validiert. Die Entscheidung einschließlich des später möglichen PostgreSQL-Pfads hält [ADR-0001](decisions/0001-lokale-relationale-persistenz.md) fest.

Diese Referenz ersetzt weder `db/schema.sql` noch die Migrationen.

## Authentifizierungsdaten

`user_account` beschreibt die technische Identität und trennt sie mit
`is_operator` ausdrücklich von `committee_member` und dessen fachlichen Rollen.
`auth_session` speichert ausschließlich Hashes des Session- und CSRF-Materials,
den Ablauf, Widerruf und die optionale Rotationsherkunft. Die Migration
`008_add_authentication_sessions.sql` ergänzt diese Tabellen für bestehende
Datenbanken; die Rohwerte werden nur beim internen Erzeugen einer Session an
den aufrufenden Service zurückgegeben. `011_add_local_password_totp_auth.sql`
ergänzt die verschlüsselte TOTP-Secret-Spalte, den zuletzt akzeptierten
TOTP-Zeitschritt und `auth_recovery_code`. Die Tabelle enthält ausschließlich
Argon2id-Hashes der einmalig ausgegebenen Recovery-Codes sowie deren
Verbrauchszeitpunkt; Einladungstoken und Betreiber-Recovery-Token bleiben als
SHA-256-Prüfwerte in `auth_token` getrennt.

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

`--init` erstellt neue Datenbanken aus `db/schema.sql` oder führt bei einem
versionierten älteren Stand die noch fehlenden Migrationen in Reihenfolge aus.
Ein nicht-leerer Bestand ohne `schema_migration`, mit unbekannter Version, einer
Historienlücke oder einer falschen Prüfsumme wird nicht automatisch repariert.
Der Healthcheck prüft dieselben Voraussetzungen und liefert bei fehlender
Readiness HTTP 503 inklusive des sicheren Fehlergrunds.

Vor ausstehenden Migrationen legt die Anwendung eine SQLite-Schutzkopie unter
`/data/backups` an. Diese Kopie schützt vor irreversiblen Änderungen, ist aber
keine allgemeine Backup-/Restore-/Exportfunktion. Jede einzelne SQL-Migration
läuft in ihrer eigenen Transaktion; der Historieneintrag wird erst nach dem
Commit geschrieben. Scheitert eine Migration, bleibt sie nicht als erfolgreich
markiert und der Server startet nicht. Bereits erfolgreich committete
Migrationen werden nicht durch einen späteren Fehler automatisch zurückgesetzt;
die Wiederherstellung aus der Schutzkopie gehört zum späteren Betriebsumfang.

`schema_migration_checksum` enthält nur Migrationsnamen und SHA-256-Prüfsummen,
keine Fachdaten. Die Readiness-Diagnose kann damit den aktuellen, Ziel- und
ausstehenden Stand sowie die angewandte Historie ausgeben, ohne sensible Daten
zu veröffentlichen. Ein zweiter gleichzeitiger Start wartet auf die
datenbankbezogene Migrationssperre und prüft danach die Historie erneut.

## Dokumentmetadaten

Die Tabelle `document` enthält die interne `storage_id`, den geprüften
Anzeigenamen, Medientyp, Größe und SHA-256-Prüfsumme. Die `storage_id` wird
serverseitig erzeugt und darf nicht aus einem Benutzerpfad stammen. Der
Dateiinhalt liegt getrennt unter `/data/documents`; die Datenbank enthält keine
unkontrollierten Dateisystempfade. Backup- und Restore-Funktionen bleiben
außerhalb von #118.
