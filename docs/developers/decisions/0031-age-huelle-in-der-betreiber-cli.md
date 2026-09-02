# ADR-0031: age-Hülle in der Betreiber-CLI

## Datum

2026-09-02.

## Status

Akzeptiert.

Supersedes [ADR-0030](0030-x25519-aes-gcm-fuer-geschuetzte-artefakte.md) ab v0.7.0.

## Kontext

Der v0.6-Vertrag verschlüsselte und entschlüsselte Artefakte im Python-Backend.
Dadurch musste eine private X25519-Identität über den Container-Exec-Kanal an die Instanz übertragen werden.
Die Betreiber-CLI soll dieselbe lokale Schlüsselgrenze für Container-Exec und spätere Transportadapter besitzen, ohne fachliche Paket- oder Restorelogik zu duplizieren.

## Entscheidung

`lzug-admin` schützt Backup und Vollexport mit `age-encryption.org/v1` und der offiziellen Go-Bibliothek `filippo.io/age`.
Der Erstvertrag unterstützt genau einen dedizierten X25519-age-Empfänger je Artefakt.
SSH-Identitäten, Passphrasen, mehrere Empfänger und eigene Kryptokonstruktionen sind ausgeschlossen.

Die CLI erzeugt und prüft die private Identität lokal, verschlüsselt beziehungsweise entschlüsselt als Stream und aktiviert ein geschütztes Ziel erst atomar nach vollständigem Erfolg.
Private Identitäten erscheinen weder in argv, Umgebung, Konfiguration, Backendauftrag, Ausgabe, Audit noch Logs.
Zulässige Quellen sind genau eine geschützte Datei, ausdrücklich gewähltes stdin oder eine verdeckte TTY-Eingabe.

Das Backend erzeugt den konsistenten ZIP-Klartextstrom unmittelbar in den age-Writer.
In Gegenrichtung nimmt es den vollständig eingelesenen Klartextstrom nur in seinem restriktiven Prüf- beziehungsweise Restore-Stagingbereich auf.
Manifest, Datenbank-, Dokument- und Fachintegrität, Migration und Aktivierung bleiben ausschließlich Backendverantwortung.

Der öffentliche Vorspann `lzug-age-artifact` Version 2 enthält nur das Verfahren `age-x25519-v1` und den vollständigen Empfängerfingerabdruck.
Dieser ist `sha256:` plus SHA-256 der UTF-8-Bytes des kanonischen öffentlichen age-Empfängers in Kleinbuchstaben-Hexdarstellung.
Der aktive öffentliche Backup-Empfänger wird als nicht geheime Singleton-Konfiguration persistent und mit einer append-only Änderungshistorie auditiert.

## Konsequenzen

Die Instanz erhält nie die private Identität und kann Artefakte ohne sie erzeugen.
Die CLI kennt weder SQLite noch Dokumentstruktur oder fachliche Restore-Regeln.
Kontrollnachricht und Binärstrom verwenden getrennte Kanäle des versionierten lokalen Protokolls.

Das proprietäre v0.6-Format `LZUGA01` wird spezifisch erkannt, aber nicht in Go reimplementiert.
Ein altes Artefakt wird mit v0.6.0 wiederhergestellt; danach folgen das reguläre Upgrade und ein neues geprüftes age-Backup.
Alte und neue Artefakte benötigen jeweils ihre ausgewiesene Identität.

Der Verlust der einzigen privaten Identität macht die zugehörigen Artefakte unwiederbringlich unlesbar.
Ein Empfängerwechsel schlüsselt vorhandene Artefakte nicht um und verlangt daher die unabhängige Aufbewahrung aller weiterhin benötigten Identitäten.

## Alternativen

- Backendverschlüsselung aus ADR-0030: würde private Identitäten weiterhin über jeden Admintransport führen.
- Eigene age-kompatible Implementierung: würde unnötige kryptografische Konstruktion und Interoperabilitätsrisiko erzeugen.
- Passphrase oder Instanzschlüssel: würde automatisierte Sicherung und externe Wiederherstellung an ein dauerhaftes Geheimnis der Instanz binden.
- Mehrfachempfänger: erhöht Format- und Betriebsumfang ohne belegten Erstbedarf.

## Referenzen

- [Lokaler Admin- und Artefaktvertrag](../data-and-contracts.md#lokaler-admin-und-artefaktvertrag)
- [CLI-Referenz](../reference/cli.md)
- [age format specification](https://age-encryption.org/v1)
- [filippo.io/age](https://pkg.go.dev/filippo.io/age)
- [Issue #571](https://github.com/lxndrp/lzug/issues/571)
