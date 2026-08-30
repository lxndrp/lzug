# Upgrade und Rollback

Upgrade und Rollback sind lokale Wartungsvorgänge über die Betreiber-CLI.
Sie laufen ausschließlich in einem dedizierten Container des gewählten Release-Images, während der reguläre Anwendungscontainer gestoppt ist.
Der Wartungscontainer erhält dasselbe persistente `/data`, veröffentlicht aber keinen Port und startet keinen Server.
Die aufgabenorientierte Bedienfolge steht ausschließlich in der kanonischen
[Betreiberanleitung](https://github.com/lxndrp/lzug/wiki/Administration-Update-und-Rollback).

## Release- und Wartungsgrenze

Das Ziel muss als unveränderlicher Digest `ghcr.io/lxndrp/lzug@sha256:…` vorliegen.
Vor der Verwendung wird dessen Herkunft gemäß dem [Releasevertrag](../releases.md) geprüft.
Die CLI akzeptiert für `upgrade` und `rollback` ausschließlich einen Container, dessen Engine-Metadaten diesen kanonischen Repo-Digest sowie die passenden OCI-Labels für Quelle, Version und Commit ausweisen.

CLI und Container müssen aus demselben annotierten SemVer-Release stammen.
Entwicklungsbuilds, bewegliche Tags, fremde Repositories, fehlende Repo-Digests und abweichende Versionen oder Revisionen werden vor dem Backendaufruf abgewiesen.
Das Backend prüft dieselbe Release-Identität erneut und verlangt `LZUG_LIFECYCLE_MAINTENANCE=true`.
Zusätzlich weist es den normalen `backend.server` als Container-Hauptprozess ab, damit eine gesetzte Variable keinen Lifecycle-Lauf im weiter bedienbaren Produktcontainer ermöglicht.

Ein Wartungscontainer kann mit Docker oder Podman nach demselben Muster vorbereitet werden:

```sh
engine=docker # oder podman
image='ghcr.io/lxndrp/lzug@sha256:<digest>'

gh attestation verify "oci://$image" --repo lxndrp/lzug
"$engine" pull "$image"
"$engine" stop lzug
"$engine" run --detach --name lzug-maintenance \
  --read-only --tmpfs /tmp:rw,noexec,nosuid,nodev \
  --env-file .env --env LZUG_LIFECYCLE_MAINTENANCE=true \
  --mount type=volume,source=lzug_data,target=/data \
  --entrypoint sleep "$image" infinity
```

Die Konfigurationsdatei wird durch die Engine gelesen; ihre Werte erscheinen nicht in Prozessargumenten oder Ausgaben der Betreiber-CLI.
Der öffentliche Backup-Empfängerschlüssel muss darin als `LZUG_BACKUP_RECIPIENT_PUBLIC_KEY` konfiguriert sein.
Der zum Image gehörende `lzug-admin`-Release wird für alle folgenden Befehle verwendet.

## Upgrade

`upgrade` prüft nacheinander Release-Identität, vorhandene Migrationshistorie, Zielpfad, Backup und Nachzustand.
Der private Backup-Empfängerschlüssel kommt ausschließlich über stdin:

```sh
private-key-provider | lzug-admin \
  --engine docker --container lzug-maintenance \
  upgrade --confirm-irreversible
```

Bei ausstehenden Migrationen ist `--confirm-irreversible` zwingend.
Ohne ausstehende Migration darf der Schalter entfallen; ein vollständiges Backup wird trotzdem erzeugt und geprüft.
Die Bestätigung ersetzt weder Backup noch Prüfung.

Das Backend verwendet ausschließlich `ArtifactService.create_backup`, `ArtifactService.verify` und `backend.database.apply_migrations`.
Es enthält keinen zweiten Backup-, SQLite- oder Migrationspfad.
Ein Backup gilt nur dann als geeignet, wenn es entschlüsselbar und vollständig ist, zum aktuellen Quellschema gehört, denselben ausstehenden Zielpfad ausweist und keine fehlende Pflichtkonfiguration meldet.

Fehlender öffentlicher Schlüssel, falscher privater Schlüssel, Beschädigung, inkompatibles Schema oder ungeprüftes Zielartefakt brechen vor der Migration ab.
Scheitert eine Migration oder die Nachprüfung, meldet der Vertrag die Phase und die geheimnisfreie Kennung des zuvor verifizierten Backups.
Der Zielserver darf dann nicht gestartet werden.
Die fail-closed Migrationshistorie und die einzelnen SQL-Transaktionen bleiben der Vertrag aus `backend.database`.

Erst nach erfolgreichem Ergebnis wird der Wartungscontainer entfernt und `LZUG_IMAGE` in der Referenzinstallation auf denselben geprüften Digest gesetzt.
Ein Fehler vor der Migration lässt den bisherigen Container wieder starten.
Nach einem Migrationsfehler bleibt die Instanz gestoppt, bis der ausgewiesene Backup- oder Wiederanlaufpfad bewusst gewählt wurde.

## Rollback

`rollback` ist die nicht mutierende Freigabegrenze für das ausgewählte ältere Release:

```sh
lzug-admin --engine docker --container lzug-maintenance rollback
```

Der Befehl gelingt nur, wenn die Migrationshistorie für diese Release-Runtime vollständig bekannt ist und keine Migration aussteht.
Danach kann der reguläre Container mit genau diesem bereits geprüften Digest gestartet werden.
Die CLI verändert beim Rollback weder Datenbank noch Dokumente.

Ein durch das ältere Release unbekanntes Schema oder ein nur vorwärts migrierbarer Stand wird vor jeder Änderung mit `rollback_not_supported` abgewiesen.
Es gibt keine Rückmigration und keine heuristische Bearbeitung von SQLite.
Soll stattdessen der vollständige Vor-Upgrade-Datenstand wiederhergestellt werden, gilt der getrennte [Restore-Vertrag](backup-restore-export.md) auf einem leeren Ziel oder im ausdrücklich bestätigten Ersetzungsmodus.

## Maschinenvertrag

Beide Befehle verwenden Protokollversion 1 und dieselben JSON-/Exit-Code-Regeln auf Windows, macOS und Linux sowie mit Docker und Podman.
Erfolgsberichte nennen ausschließlich Release-Identität, Digest, Schema- und Migrationsnamen, Backup-Kennung und abgeschlossene Phasen.
Private Schlüssel, Konfigurationswerte, Pfade und Fachdaten werden nicht ausgegeben.

`release_artifact_unverified`, `maintenance_required` und Lifecycle-Ausführungsfehler verwenden Exit 33.
`irreversible_confirmation_required` verwendet Exit 29.
`rollback_not_supported` und `migration_failed` verwenden Exit 28; ungültige oder nicht geeignete Backups behalten die Exit-Codes 26 und 27 des Artefaktvertrags.
