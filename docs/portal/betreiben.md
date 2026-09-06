# Self-Hosting und Betrieb

Diese Anleitung ist der lineare Nachweis für eine einzelne selbst betriebene lzug-Instanz.
Sie ergänzt die ausführlichen kanonischen Betriebsseiten im [Handbuch](/betreiben/administration/),
ohne einen technischen Produkt-Wizard zu erzeugen.

## Vor dem Start

Verwenden Sie nur ein [veröffentlichtes Release](https://github.com/lxndrp/lzug/releases) mit zueinander passendem OCI-Image,
`compose.yaml` und `lzug-admin`.
Prüfen Sie die Asset-Digests und die Build-Identität wie in der [Installationsanleitung](/betreiben/installation-und-konfiguration/) beschrieben.
Planen Sie ein dauerhaftes `/data`-Volume und einen HTTPS-Reverse-Proxy außerhalb des Hosts ein.

Bei einem Abbruch bleibt der zuletzt erfolgreich geprüfte Schritt maßgeblich.
Entfernen oder überschreiben Sie keine Daten, Tokens oder Schlüssel, um einen Schritt zu wiederholen.
Lesen Sie die zugehörige Fehlerausgabe,
korrigieren Sie nur die benannte Voraussetzung und führen Sie den Schritt erneut aus.

## Nachweiskette

1. Laden und prüfen Sie die Release-Artefakte.
2. Konfigurieren Sie das persistente Datenvolume und starten Sie den Container mit der Referenz-Compose-Datei.
3. Belegen Sie `health` und `ready`; erst `ready` zeigt den einsatzfähigen Anwendungs- und Datenbankzustand.
4. Legen Sie das erste Betreiberkonto ausschließlich mit `lzug-admin` an.
5. Bootstrapen Sie den Ausschuss und ordnen Sie den ersten Vorsitz zu.
   Betreiberrechte und Ausschussrechte bleiben getrennt: Der Betreiber darf dadurch keine fachliche Arbeit im Ausschuss ausführen.
6. Führen Sie `lzug-admin system doctor` erfolgreich aus und bewahren Sie nur die geheimnisfreie Diagnose auf.
7. Erzeugen Sie einen separaten Backup-Empfängerschlüssel,
   aktivieren Sie ihn lokal und erstellen sowie verifizieren Sie das erste Backup.
8. Übergeben Sie danach die fachliche Einrichtung an den Vorsitz.
   Der Vorsitz meldet sich regulär an,
   erkennt Ausschuss und Prüfungshalbjahr in der Oberfläche und führt die fachliche Einrichtung dort fort.

## Konten, Bootstrap und Diagnose

Die genaue Reihenfolge mit sicheren Eingabewegen,
Fehlergrenzen und erwarteten Ergebnissen steht in [Installation und Konfiguration](/betreiben/installation-und-konfiguration/).
Der Betreiber verwaltet Konto- und Ausschusszuordnung über die lokale CLI;
fachliche Terminplanung bleibt danach der gleichberechtigten Ausschussrolle vorbehalten.

`lzug-admin system status` und `lzug-admin system doctor` sind nicht mutierend.
Bei einem fehlgeschlagenen `doctor` beheben Sie zuerst die gemeldete lokale Voraussetzung,
bevor Sie einen Bootstrap-, Backup- oder Fachschritt wiederholen.

## Erstes Backup

Die private age-Identität bleibt außerhalb des Hosts,
Containers und `/data`-Volumes.
Erst nach erfolgreichem `backup verify` ist das Artefakt verwendbar.
Die vollständige Schlüssel-, Backup-, Restore- und Fehleranleitung steht unter
[Backup, Restore und Vollexport](/betreiben/backup-pruefung-und-restore/).

## Unterstützung und Sicherheit

Für eine selbst betriebene Instanz ist zuerst der vom Betreiber konfigurierte lokale Kontakt zuständig.
Projektbezogene Fragen von Betreibern gehören in den öffentlichen Projektkanal,
nicht in eine Produktivinstanz.
Sicherheitslücken folgen ausschließlich dem vertraulichen Verfahren in [SECURITY.md](https://github.com/lxndrp/lzug/blob/master/SECURITY.md).
Lokale Sicherheitsvorfälle und deren Meldung an Betroffene bleiben Betreiberverantwortung.
