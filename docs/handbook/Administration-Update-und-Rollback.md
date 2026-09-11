# Update und Rollback

Die Zuständigkeiten folgen
[ADR-0033](https://github.com/lxndrp/lzug/blob/master/docs/developers/decisions/0033-aio-betrieb-admintransport-und-lifecycle.md).
Die Containerplattform bezieht das geprüfte Release-Image, ersetzt den Container
und startet es mit den vorhandenen Daten.
`lzug-admin` verändert weder Images noch Containerzustände.
Es gibt keinen separaten Wartungs- oder Migrationsprozess.

## Imagewechsel vorbereiten

Lesen Sie die Release Notes und prüfen Sie die Herkunft des veröffentlichten
Zielimages nach dem [Installationsverfahren](Administration-Installation-und-Konfiguration).
Planen Sie ein Wartungsfenster.
Konfigurieren Sie den öffentlichen Backup-Empfänger vor dem Imagewechsel und
halten Sie dessen privaten Schlüssel auf dem Bedienrechner verfügbar.
Erstellen und prüfen Sie ein vollständiges Backup nach dem
[Backup- und Restore-Verfahren](Administration-Backup-Pruefung-und-Restore).
Die CLI prüft keine Image-Referenzen oder OCI-Labels; diese Prüfung gehört zur
Bereitstellung durch den Betreiber.

Nach dem Imagewechsel erkennt derselbe bereits laufende Backendprozess den
Schema- und Kompatibilitätsstand.
`--init` initialisiert leere Datenbestände; vorhandene Daten werden dabei nicht
mehr automatisch migriert.
Bei ausstehenden Migrationen bleibt die Anwendung live, aber nicht ready.
Das Frontend erklärt die vorübergehende Nichtverfügbarkeit und normale
Fachaufträge bleiben gesperrt.
Ohne ausstehende Migration und bei kompatiblen Daten ist die Anwendung ready;
eine Migrationsfreigabe ist dann nicht erforderlich.

## Datenübergang prüfen und freigeben

Verwenden Sie den bereitgestellten lokalen Endpunkt gemäß der
[CLI-Konfiguration](Administration-Installation-und-Konfiguration).
Ein extern weitergeleiteter Endpunkt verwendet denselben Socketvertrag.
Bereitstellung, SSH und Lebensdauer einer Weiterleitung bleiben außerhalb der
Anwendung und ihres Testversprechens.
Container-Exec ist kein Migrationstransport.

```sh
lzug-admin --endpoint unix:///run/lzug-admin/admin.sock system status
lzug-admin --endpoint unix:///run/lzug-admin/admin.sock upgrade status
```

`upgrade status` ist nicht mutierend.
Es nennt den Build der laufenden Anwendung, Quell- und Zielschema, ausstehende
Migrationen, Freigabemöglichkeit und Rollbackgrenze.
Entwicklungsbuilds, unbekannte Schemata und ein bereits fehlgeschlagener oder
unterbrochener Datenübergang erhalten keine reguläre Migrationsfreigabe.

```sh
lzug-admin --endpoint unix:///run/lzug-admin/admin.sock upgrade apply \
  --backup-output ./lzug-vor-migration.lzug \
  --identity-file /geschuetzter/pfad/backup.agekey \
  --confirm-irreversible
```

Die CLI zeigt vor der interaktiven Bestätigung den ausgewählten Endpunkt,
Versions- und Schemaplan sowie die Restoregrenze.
Im nicht interaktiven Betrieb ist zusätzlich `--force` erforderlich.
`--force` ersetzt weder `--confirm-irreversible` noch die Sicherungsprüfung.
Der interaktive Einstieg `lzug-admin cli` nutzt dieselben Commands und Regeln.

Der Backendprozess erzeugt ein vollständiges Sicherungspaket aus seinem
unveränderten Quellbestand.
Die CLI schützt es mit age, veröffentlicht die lokale Datei erst nach
vollständigem Erfolg und entschlüsselt diese anschließend mit dem lokalen
privaten Schlüssel.
Das Backend prüft das zurückübertragene Paket nicht mutierend auf Vollständigkeit,
Integrität, Schema und erforderliche Konfiguration.
Vor der Migration prüft es erneut das exakte Paket gegen seinen eigenen
Sicherungsnachweis und den freigegebenen Plan.
Ein vom Client behauptetes `verified: true` genügt nicht.

Fehlender Empfänger, falscher Schlüssel, beschädigtes, unvollständiges,
instanzfremdes oder inkompatibles Backup verhindern die Migration.
Private Schlüssel und Passphrasen verlassen den Bedienrechner nicht und
erscheinen weder in Argumenten noch in Logs, Audit oder Fehlerdetails.

## Abschluss und Verbindungsverlust

Die Migration läuft unter Transaktions-, Sperr- und Lifecyclekoordination des
bereits laufenden Backendprozesses.
Erst erfolgreiche Migration, Nachprüfung und gespeicherter Auftragsabschluss
geben Readiness und Fachbetrieb frei.
Prüfen Sie anschließend `system status`, `/api/ready` und eine fachliche
Stichprobe über die reguläre Oberfläche.

Eine verlorene CLI-Verbindung beendet oder wiederholt eine bereits laufende
Migration nicht.
Bewahren Sie die ausgegebene Auftrags-ID auf und prüfen Sie `system status`
beziehungsweise `upgrade status --job-id <UUID>`.
Die Socket-Auftrags-ID entspricht bei einer begonnenen Migration der dauerhaft
gespeicherten Runtime-Auftrags-ID.
Der letzte exklusive Auftrag bleibt nach Neustart erhalten; ältere nicht mehr
vorhandene Aufträge werden nicht als erfolgreich behauptet.

Bei Migrations- oder Nachprüfungsfehler bleibt die Anwendung live/not-ready und
diagnostizierbar.
Ein Neustart wiederholt keinen Auftrag und entfernt die Wiederherstellungssperre
nicht.
Ein Sicherungsnachweis aus einem früheren Prozess erlaubt keine neue Mutation.
Nutzen Sie den dokumentierten Restore- oder Supportweg.
Verändern Sie SQLite, Migrationstabellen oder das Runtime-Journal nicht manuell.

## Rollback- und Restoregrenze

`upgrade rollback` lehnt mit `rollback_not_supported` und Exit `28` ab und erklärt
die Grenze vor jeder Änderung.
Es führt weder Containerrollback noch Rückwärtsmigration aus.
Ein Image-Rollback gehört zur Containerplattform; die dann gestartete Anwendung
prüft selbst, ob sie das vorhandene Schema kennt und sicher verwenden kann.
Ein unbekanntes neueres Schema bleibt nicht ready.

Nach einer Datenmigration erfordert die Rückkehr zum früheren Datenstand ein
vollständiges, geprüftes Backup und ein mit dessen Format und Schema kompatibles
Image.
Der [Restore-Vertrag](Administration-Backup-Pruefung-und-Restore) auf einer
leeren Instanz oder mit ausdrücklicher Ersatzfreigabe ist ein eigener Vorgang.
Ein Restore durch ein neueres Image kann wieder vorwärts migrieren und stellt
deshalb keine Rückwärtsmigration dar.
Ist kein kompatibler Wiederherstellungs- oder Vorwärtspfad belegt, bleibt die
Instanz gesperrt und benötigt den
[Supportweg](Administration-Verantwortung-Grenzen-und-Support).

Maschinenlesbare Ergebnisse und Exit-Codes folgen der
[CLI-Referenz](https://github.com/lxndrp/lzug/blob/master/docs/developers/reference/cli.md).
Bewahren Sie Build, Plan, Auftrags-ID, Backup-Artefakt-ID und Ergebnis als
technischen Nachweis auf; Secrets und Fachdaten gehören nicht in diesen Nachweis.
