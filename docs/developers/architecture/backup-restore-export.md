# Backup, Restore und Vollexport

Backup und Vollexport sind zwei getrennte Artefaktarten an derselben lokalen Betriebsgrenze.
Ein Backup stellt eine Instanz vollständig wieder her und enthält deshalb auch den anwendungseigenen Authentifizierungsschlüssel.
Ein Vollexport überträgt fachliche Daten und Dokumente in einem offenen Format, enthält aber keine Authentifizierungs-, Zugangs-, Sitzungs-, Zustell- oder Betriebsgeheimnisse.

Beide Vorgänge laufen ausschließlich über `python -m backend.admin --protocol 1` im Anwendungscontainer.
Es gibt dafür keine HTTP-Route, keine OpenAPI-Operation und keine fachliche UI-Berechtigung.
Die portable Betreiber-CLI orchestriert diesen Vertrag über interaktives Container-`exec`, ohne SQLite oder die Paketlogik selbst zu kennen.

## Schutzformat

Ein Artefakt beginnt mit `LZUGA01\n`, der Länge des JSON-Vorspanns als vier Byte Big Endian und dem kanonischen JSON-Vorspann.
Der Vorspann enthält ausschließlich Format und Version, `x25519-hkdf-sha256-aes256-gcm` als Schutzverfahren, den SHA-256-Fingerabdruck des Empfängerschlüssels sowie ephemeren öffentlichen Schlüssel, Nonce und Tag-Länge.
Dateinamen, Instanzdaten und Geheimnisse stehen erst im geschützten Paket.

Der Empfängerschlüssel verwendet rohes X25519-Schlüsselmaterial in diesen versionierten Eingabeformen:

```text
x25519:<base64url der 32 öffentlichen Bytes>
x25519-private:<base64url der 32 privaten Bytes>
```

Für jedes Artefakt wird ein ephemeres X25519-Schlüsselpaar erzeugt.
HKDF-SHA-256 mit dem Kontext `lzug-protected-artifact-v1` leitet einen einmaligen AES-256-GCM-Schlüssel ab; der gesamte Vorspann ist als Additional Authenticated Data gebunden.
Die Implementierung verwendet `cryptography`, verschlüsselt und entschlüsselt in Blöcken und veröffentlicht erst nach erfolgreicher Paket- und Schutzprüfung durch atomare Umbenennung.

Der private Empfängerschlüssel wird nur im JSON von stdin übergeben.
Er erscheint nicht in argv, Antwort, Fehlertext oder technischem Operationsnachweis und wird nicht auf der Instanz gespeichert.
Für automatische Backups enthält `LZUG_BACKUP_RECIPIENT_PUBLIC_KEY` ausschließlich den öffentlichen Schlüssel.

## Geschütztes Paket

Das geschützte ZIP-Paket verwendet unkomprimierte Einträge, damit Größen- und Speichergrenzen vor der Extraktion belastbar geprüft werden können.
`manifest.json` enthält Artefakt-ID und -art, Anwendungs-, Schema- und Formatversion, Erstellungs- und Snapshot-Zeitpunkt, Instanzkennung, vollständige Inhaltsliste mit Größe und SHA-256-Prüfsumme, Anzahlen, Konfigurationsabhängigkeiten und Kompatibilitätsgrenzen.
Pfade mit Traversierung, Symlinks, Duplikate, nicht deklarierte Inhalte und komprimierte Einträge werden abgewiesen.

Ein Backup enthält:

- `payload/database.sqlite` als konsistenten SQLite-Snapshot,
- `payload/documents/<storage-id>` für jedes referenzierte Dokument,
- `payload/keys/key-1.bin` als opakes Authentifizierungsschlüsselmaterial.

Das Manifest bindet den Authentifizierungsschlüssel durch SHA-256 über Datenbank-Prüfsumme und Schlüsselmaterial an genau diesen Datenstand.
Prüfung und Restore entschlüsseln mit diesem Schlüssel jedes vorhandene TOTP-Secret, bevor eine Zielinstanz verändert wird.
Der Schlüssel wird beim Restore unverändert als persistente `/data/.lzug-auth.key` mit Modus `0600` aktiviert.

## Konsistenter Snapshot

Anwendungsseitige Mutationen halten eine gemeinsame Lesesperre; Dokumentservice und Datenbanktransaktion umfassen dabei dieselbe Mutationsgrenze.
Die kurze Snapshot-Phase nimmt die exklusive Snapshot-Sperre, wartet dadurch bereits laufende Mutationen ab und lässt Leser weiterarbeiten.
Sie kopiert SQLite über dessen Online-Backup-API aus dem WAL-Betrieb und legt unveränderliche Hardlinks auf den dazu passenden Dokumentbestand an.
Danach endet die Schreibsperre; Integritätsprüfung, Manifest, Paketierung und Verschlüsselung arbeiten nur noch auf dem Snapshot.

Fehlende oder verwaiste Dokumente, temporäre Einträge, Größen- oder Prüfsummenabweichungen verhindern die Veröffentlichung.
Temporäre Snapshot-, Paket- und Schutzdateien beginnen mit einem Punkt und werden bei Erfolg, Fehler oder erneutem Lauf entfernt.

## Nicht mutierende Prüfung

`artifact-verify` validiert Vorspann, Empfängerschlüssel, GCM-Schutz, Paketstruktur, Vollmanifest und alle Inhaltsprüfsummen.
Bei Backups folgen Schema- und Migrationskompatibilität, SQLite- und Fremdschlüsselintegrität, Dokumentbeziehungen sowie Schlüsselbindung und TOTP-Entschlüsselung.
Beim Vollexport werden Format, Dokumentliste und der Ausschluss verbotener Tabellen und Felder geprüft.
Der Vorgang schreibt weder Fachdaten noch einen Operationsnachweis.

## Restore

Ein Restore durchläuft die Phasen `precheck`, `prepared_restore`, `migration`, `postcheck` und `activation`.
Entschlüsselung und vollständige Prüfung geschehen vor der ersten Zielmutation.
Auf einer leeren Installation wird der vorbereitete Stand direkt aktiviert; ein nicht leeres Ziel verlangt `replace: true`.
Im Ersetzungsmodus wird unter der Aktivierungssperre zuerst ein geschütztes `pre-restore`-Backup des bisherigen Standes für denselben Empfänger erzeugt.

Unterstützte ältere Schemastände werden ausschließlich durch `backend.database.apply_migrations` im vorbereiteten Verzeichnis weiterentwickelt.
Unbekannte neuere und ältere als `009_harden_migration_history.sql` ausgewiesene Stände werden vor der Aktivierung abgewiesen.
Nach Migration werden SQLite, Fremdschlüssel, Dokumente, TOTP-Secrets, Instanzkennung und aktuelle Schemaversion erneut geprüft.
Die Aktivierung ersetzt Datenbank, Dokumentverzeichnis und Authentifizierungsschlüssel zusammen; ein Fehler verschiebt den bisherigen Stand kontrolliert zurück.

Der Restore entfernt aktive Sitzungen, offene Einladungs- und Recovery-Vorgänge, Recovery-Codes sowie technische Zustell-Claims.
Konten, Rollen, Passwort-Hashes, TOTP- und Passkey-Zustand, Kalenderfeeds, Push-Registrierungen, Benachrichtigungen und Zustellhistorie bleiben erhalten.
Nicht mehr aktuelle offene Folgeaufträge bereits geschlossener Wiedereröffnungen werden abgeschlossen.

`LZUG_REQUIRED_EXTERNAL_CONFIG` nennt kommasepariert die Namen externer `LZUG_*`-Variablen, die für diese Installation zwingend sind.
Das Manifest enthält nur Namen und Konfigurationsstatus, niemals Werte.
Fehlende Pflichtkonfiguration ergibt `not_ready`; ein am Quellsystem konfigurierter, am Ziel fehlender optionaler E-Mail- oder Web-Push-Kanal ergibt `restricted`.
Abweichende externe URL und Zeitzoneneinstellungen erscheinen ausschließlich als geänderte Variablennamen im Bericht.

## Lokaler Protokollvertrag

Alle Anfragen sind ein einzelnes JSON-Objekt auf stdin; Antworten sind ein einzelnes geheimnisfreies JSON-Objekt auf stdout.
Die Python-Grenze unterstützt:

```json
{"version":1,"command":"backup-create","arguments":{}}
{"version":1,"command":"artifact-verify","arguments":{"artifact":"backup-...lzug","recipient_private_key":"x25519-private:..."}}
{"version":1,"command":"backup-restore","arguments":{"artifact":"backup-...lzug","recipient_private_key":"x25519-private:...","replace":false}}
{"version":1,"command":"full-export","arguments":{"recipient_public_key":"x25519:..."}}
```

Erfolgsberichte enthalten Artefaktart und -ID, Quell- und Zielversionen, Snapshot-Zeitpunkt, Anzahlen, Migrationen, Rücksetzungen, Konfigurationsabweichungen und Readiness soweit für den Vorgang relevant.
Fehler enthalten `class`, `message` und bei Artefaktvorgängen die genaue `phase`.
Die stabilen Python-Exit-Codes `26` bis `29`, `32` und `33` unterscheiden ungültiges Artefakt, Empfängerschlüssel, Inkompatibilität, fehlende Ersetzungsbestätigung, Speicherplatz und sonstigen Artefaktvorgang.
Die Betreiber-CLI reicht den maschinenlesbaren Bericht und die stabilen Backend-Exit-Codes unverändert weiter.
Damit verhalten sich Docker und Podman sowie die portablen Windows-, macOS- und Linux-Builds am gemeinsamen Vertrag identisch.

## Offener Vollexport

Der Vollexport verwendet einen ausdrücklich in stdin angegebenen öffentlichen Empfängerschlüssel und kann nicht ungeschützt erzeugt werden.
Im geschützten Paket liegen:

- `export/data.json` mit fachlichen Tabellen, stabilen `<tabelle>:<id>`-Exportkennungen, Attributen und expliziten Fremdschlüsselbeziehungen,
- `export/documents.json` mit Dateipfad, Name, Medientyp, Größe und Prüfsumme,
- `export/documents/` mit den vorhandenen Binärdateien,
- `export/value-lists.json` mit verwendeten Codewerten und ihrer Feldzuordnung,
- `export/full-export-v1.schema.json` als JSON-Schema für `data.json`,
- `export/README.txt` als menschenlesbare Kurzbeschreibung.

Der kanonische Schema-Vertrag liegt zusätzlich unter [full-export-v1.schema.json](../reference/full-export-v1.schema.json).
Ausgeschlossen sind insbesondere Konto- und Authentifizierungstabellen, Sitzungen, Token, Recovery-Codes, Kalenderfeed-Token, Push-Endpunkte, Zustell-Claims, technische Operations- und Migrationsdaten sowie alle bekannten geheimen Felder.
Der Export ist kein Restore-Eingang.

## Betreiberverantwortung

lzug plant, rotiert, überträgt und löscht Artefakte nicht automatisch.
Betreiber verantworten externen privaten Schlüssel, Zielkopien, Fernspeicher, Aufbewahrung und regelkonforme Löschung.
Passphrasen, mehrere Schutzmodi, Teilrestore, Zusammenführung, Downgrade, Anwendungsaustausch und Schlüsselrotation gehören nicht zu diesem Vertrag.
