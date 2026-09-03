# Backup, Restore und Vollexport

Ein vollständiges Backup enthält Datenbank, Dokumente und anwendungseigene Authentifizierungsschlüssel.
Ein Vollexport enthält fachliche Daten und Dokumente, aber keine Authentifizierungs-, Sitzungs-, Zustell- oder Betriebsgeheimnisse und ist kein Restore-Eingang.

Ab v0.7.0 erzeugt `lzug-admin` geschützte Artefakte im offenen age-Format.
Der private Schlüssel verbleibt immer auf dem Bedienrechner; das Backend erhält nur den öffentlichen Backup-Empfänger und Klartext-Paketströme innerhalb des lokalen Container-Transports.

## Schlüssel erzeugen und unabhängig sichern

Erzeugen Sie ein ausschließlich für lzug-Backups verwendetes X25519-age-Schlüsselpaar:

```console
lzug-admin recipient-key generate \
  --identity-file /geschuetzter/pfad/lzug-backup.agekey \
  --recipient-file /geschuetzter/pfad/lzug-backup.agepub
```

Die private Datei wird neu und restriktiv geschützt angelegt; vorhandene Ziele werden nicht überschrieben.
Sichern Sie sie unabhängig vom lzug-Host, Container, `/data`-Volume und den Backup-Artefakten.
Ohne diese Identität sind die zugehörigen Artefakte nicht wiederherstellbar.

Prüfen Sie eine private oder öffentliche Datei ohne Ausgabe des privaten Werts:

```console
lzug-admin recipient-key inspect --key-file /geschuetzter/pfad/lzug-backup.agekey
```

Vergleichen Sie den vollständigen `sha256:`-Fingerabdruck über einen verifizierten Kanal.

## Backup-Empfänger aktivieren und wechseln

Setzen Sie den ersten Empfänger mit einem lokalen Besitznachweis:

```console
lzug-admin --container "$CONTAINER" backup recipient set \
  --identity-file /geschuetzter/pfad/lzug-backup.agekey
```

`backup recipient show` zeigt nur den öffentlichen Empfänger, das Verfahren, den Fingerabdruck und den Aktivierungszeitpunkt.
Ein Wechsel verlangt eine neue lokale Identität und bestätigt den alten und neuen Fingerabdruck:

```console
lzug-admin --container "$CONTAINER" backup recipient replace \
  --identity-file /geschuetzter/pfad/lzug-backup-neu.agekey
```

Nichtinteraktive Automatisierung ergänzt `--force`.
Der Wechsel schlüsselt vorhandene Artefakte nicht um; bewahren Sie alte Identitäten deshalb bis zum Ende der Aufbewahrung der zugehörigen Artefakte auf.
Der Empfänger kann nicht ersatzlos gelöscht werden.

Eine vorhandene syntaktisch gültige v0.6-Konfiguration über `LZUG_BACKUP_RECIPIENT_PUBLIC_KEY` wird beim Upgrade einmalig übernommen.
Danach ist die auditierte Datenbankkonfiguration maßgeblich.

## Backup erzeugen und prüfen

Die Zieldatei liegt auf dem Bedienrechner und muss neu sein:

```console
lzug-admin --container "$CONTAINER" backup create \
  --output ./lzug-backup.lzug

lzug-admin --container "$CONTAINER" backup verify \
  --artifact ./lzug-backup.lzug \
  --identity-file /geschuetzter/pfad/lzug-backup.agekey
```

Ein Backup gilt erst nach Exit `0` und erfolgreicher vollständiger Prüfung als verwendbar.
`artifact inspect --artifact ./lzug-backup.lzug` zeigt ohne Schlüssel nur Format, Verfahrensfassung und benötigten Fingerabdruck.
Protokollieren Sie Artefaktdigest, Fingerabdruck, Zeitpunkt, CLI-/Releaseversion und Prüfergebnis, aber keine Identität oder Fachdaten.

## Vollexport erzeugen und prüfen

Der Export erhält genau einen ausdrücklich autorisierten öffentlichen age-Empfänger und verändert die Backup-Konfiguration nicht:

```console
lzug-admin --container "$CONTAINER" export create \
  --recipient 'age1...' \
  --output ./lzug-export.lzug
```

Bestätigen Sie interaktiv den vollständigen Fingerabdruck oder verwenden Sie nichtinteraktiv `--force`.
Der Empfänger prüft anschließend lokal:

```console
lzug-admin --container "$CONTAINER" export verify \
  --artifact ./lzug-export.lzug \
  --identity-file /geschuetzter/pfad/export.agekey
```

## Restore durchführen

Prüfen Sie Artefakt, Identität, freien Speicher, Zielrelease und erforderliche externe Konfiguration vor der Mutation.
Ein leeres Ziel wird mit folgendem Befehl wiederhergestellt:

```console
lzug-admin --container "$CONTAINER" backup restore \
  --artifact ./lzug-backup.lzug \
  --identity-file /geschuetzter/pfad/lzug-backup.agekey
```

Ein nicht leeres Ziel benötigt zusätzlich `--replace`.
Die CLI erzeugt davor ein neues age-geschütztes Sicherheitsbackup im Verzeichnis des Eingabeartefakts; erst danach darf das Backend den vollständig vorbereiteten Stand aktivieren.
Prüfen und archivieren Sie den gemeldeten Pfad des Sicherheitsartefakts.

Nach dem Restore prüfen Sie mindestens:

1. `lzug-admin system status` und `lzug-admin system doctor` melden den erwarteten Stand.
2. Die Anwendung ist ready und eine berechtigte Anmeldung funktioniert.
3. Prüflinge, Dokumente, Ausschüsse und bestätigte Termine sind stichprobenartig vorhanden.
4. Frühere Sitzungen und kurzlebige Recovery-Zustände sind wie dokumentiert zurückgesetzt.
5. Erforderliche externe Kanäle und Konfigurationen wurden neu validiert.

## Private Identität über stdin oder TTY

Statt einer Datei kann genau eine ausdrücklich gewählte Quelle verwendet werden:

```console
lzug-admin ... backup verify --artifact ./lzug-backup.lzug --identity-stdin
lzug-admin ... backup verify --artifact ./lzug-backup.lzug --identity-prompt
```

`--identity-stdin` verlangt umgeleitetes stdin; `--identity-prompt` verlangt ein TTY und deaktiviert Echo.
Der Schlüsselwert gehört nie in argv, Umgebungsvariablen, normale Konfiguration, Shell-Verlauf, Tickets oder Logs.

## v0.6.0-Artefakte

v0.7.0 erkennt das proprietäre v0.6-Format eindeutig, liest es aber bewusst nicht.
Gehen Sie für ein solches Artefakt ausschließlich so vor:

1. Verwenden Sie das veröffentlichte v0.6.0-Containerabbild und die passende v0.6.0-CLI mit der damaligen privaten Identität.
2. Stellen Sie das Artefakt in einer isolierten v0.6.0-Instanz wieder her und nehmen Sie den Datenstand ab.
3. Erzeugen und prüfen Sie vor dem Versionswechsel ein aktuelles v0.6.0-Backup.
4. Führen Sie das reguläre Upgrade auf v0.7.0 aus.
5. Erzeugen Sie sofort ein neues age-Backup und prüfen Sie es mit der neuen CLI.

Es gibt keine automatische Umschlüsselung und keinen Mischbetrieb.
Bewahren Sie v0.6.0-Releaseartefakte und die damalige Identität so lange auf, wie v0.6-Backups aufbewahrt werden.

## Verlust und Fehler

- Bei Verlust der privaten Identität existiert kein Wiederherstellungsweg für ihre Artefakte.
- Ein falscher Fingerabdruck, eine unsichere Schlüsseldatei, ein beschädigter Vorspann oder Ciphertext und eine fehlgeschlagene Backendprüfung brechen fail-closed ab.
- Vorhandene Zieldateien werden nicht überschrieben; kontrollierbare temporäre Ausgaben werden bei Fehler entfernt.
- Verändernde Operationen werden nach Transport- oder Streamabbruch nicht automatisch wiederholt.
- Backupplanung, Fernübertragung, Aufbewahrung und automatische Rotation bleiben Betreiberverantwortung.
