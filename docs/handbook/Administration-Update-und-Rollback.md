# Update und Rollback

Diese Verfahren stehen ab `v0.6.0` zur Verfügung.
Sie werden ausschließlich mit veröffentlichten Release-Artefakten in einem
dedizierten Wartungscontainer ausgeführt.
Der normale Anwendungscontainer ist dabei gestoppt; der Wartungscontainer
veröffentlicht keinen Port und startet keinen Server.

Ein Update des Image-Verweises allein ist kein unterstütztes Upgrade.
Ein Rollback ist keine Datenbank-Rückmigration.

## Zielrelease und Wartungsfenster vorbereiten

1. Lesen Sie Release Notes, bekannte Grenzen und den ausgewiesenen
   Migrationsumfang des Zielreleases.
2. Planen Sie ein Wartungsfenster und sperren Sie den öffentlichen Zugriff am
   Reverse Proxy.
3. Prüfen Sie, dass das konfigurierte Backup-Empfängerschlüsselpaar verfügbar
   ist und ein aktuelles vollständiges Backup nicht mutierend verifiziert wurde.
4. Wählen Sie den unveränderlichen GHCR-Digest des veröffentlichten Zielreleases
   und prüfen Sie dessen Herkunft.
5. Verwenden Sie `lzug-admin` aus demselben Release wie das Zielimage.

```sh
ENGINE=docker
TARGET_IMAGE='ghcr.io/lxndrp/lzug@sha256:<digest>'

gh attestation verify "oci://$TARGET_IMAGE" --repo lxndrp/lzug
"$ENGINE" pull "$TARGET_IMAGE"
./lzug-admin --version
./lzug-admin --build-metadata
```

Für Podman setzen Sie `ENGINE=podman`.
Die CLI prüft zusätzlich selbst den kanonischen Repo-Digest sowie die
OCI-Labels für Quelle, Version und Commit.
Entwicklungsbuilds, bewegliche Tags, fremde Repositories und eine von der CLI
abweichende Release-Identität werden vor dem Backendaufruf abgewiesen.

## Wartungscontainer starten

Erstellen Sie außerhalb des Repositorys eine temporäre, nur für den
Service-Account lesbare Env-Datei mit der wirksamen Laufzeitkonfiguration.
Der aktive öffentliche Backup-Empfänger liegt ab v0.7.0 auditiert im
Datenbestand; der private Empfängerschlüssel gehört weder in diese Datei noch
in den Container.

Stoppen Sie die Referenzinstallation und starten Sie den Wartungscontainer mit
demselben persistenten Volume:

```sh
DATA_VOLUME="${LZUG_DATA_VOLUME:-lzug_data}"
MAINTENANCE_ENV_FILE=/geschuetzter/pfad/lzug-maintenance.env

"$ENGINE" compose -f compose.yaml stop lzug
"$ENGINE" run --detach --name lzug-maintenance \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,nodev \
  --env-file "$MAINTENANCE_ENV_FILE" \
  --env LZUG_LIFECYCLE_MAINTENANCE=true \
  --mount "type=volume,source=${DATA_VOLUME},target=/data" \
  --entrypoint sleep "$TARGET_IMAGE" infinity
```

Der Wartungscontainer darf keinen Port veröffentlichen.
Das Backend weist den Lifecycle-Aufruf außerdem ab, wenn der normale
`backend.server` der Container-Hauptprozess ist.

## Upgrade durchführen

`upgrade apply` prüft Release-Identität, Migrationshistorie, Zielpfad und
Wartungsgrenze.
Die CLI erzeugt davor lokal ein age-geschütztes vollständiges Backup des
aktuellen Datenstands und prüft es mit der lokalen privaten Identität, bevor
eine Migration beginnt.

Bei ausstehenden Migrationen ist die ausdrückliche Bestätigung zwingend:

```sh
PRIVATE_KEY_FILE=/geschuetzter/pfad/lzug-backup.agekey
./lzug-admin --engine "$ENGINE" --container lzug-maintenance \
  upgrade apply \
  --backup-output ./lzug-pre-upgrade.lzug \
  --identity-file "$PRIVATE_KEY_FILE" \
  --confirm-irreversible
```

Die Bestätigung ersetzt weder Backup noch kryptographische und fachliche
Prüfung.
Ohne ausstehende Migration darf `--confirm-irreversible` entfallen; das
vollständige Backup wird trotzdem erzeugt und geprüft.

Ein geeignetes Backup muss entschlüsselbar und vollständig sein, exakt zum
Quellschema und zum ausstehenden Zielpfad passen und darf keine fehlende
Pflichtkonfiguration melden.
Fehlender öffentlicher Empfänger, falsche private Identität, Beschädigung,
inkompatibles Schema oder ungeprüftes Zielimage brechen vor der Migration ab.

## Erfolgreiches Upgrade aktivieren

Aktivieren Sie das Zielimage erst nach `ok: true` und vollständig
abgeschlossenen Phasen:

```sh
"$ENGINE" rm --force lzug-maintenance
export LZUG_IMAGE="$TARGET_IMAGE"
"$ENGINE" compose -f compose.yaml up -d

CONTAINER_ID="$("$ENGINE" compose -f compose.yaml ps -q lzug)"
CONTAINER="$("$ENGINE" inspect --format '{{.Name}}' "$CONTAINER_ID")"
CONTAINER="${CONTAINER#/}"
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" system doctor
curl -fsS http://127.0.0.1:8000/api/ready
```

Prüfen Sie anschließend über HTTPS Anmeldung, erwartete Ausschusszuordnung und
eine fachliche Stichprobe.
Entfernen Sie die temporäre Wartungs-Env-Datei und geben Sie den Reverse Proxy
erst nach erfolgreicher Abnahme wieder frei.

## Fehlergrenzen beim Upgrade

Ein Fehler vor der Migration verändert den Datenstand nicht.
Entfernen Sie den Wartungscontainer und starten Sie den unveränderten bisherigen
Anwendungscontainer nur dann erneut:

```sh
"$ENGINE" rm --force lzug-maintenance
"$ENGINE" compose -f compose.yaml start lzug
```

Nach einem Migrations- oder Nachprüfungsfehler bleibt die Instanz gestoppt.
Die JSON-Antwort nennt Fehlerphase und geheimnisfreien Namen des zuvor
verifizierten Backups.
Starten Sie weder altes noch neues Image, solange die Schema-Kompatibilität
nicht eindeutig feststeht.

Für die Rückkehr zum vollständigen Vor-Upgrade-Datenstand gilt ausschließlich
der getrennte
[Restore-Vertrag](Administration-Backup-Pruefung-und-Restore) auf einer leeren
Instanz oder mit ausdrücklich bestätigtem `--replace`.
Der Restore muss von einem veröffentlichten Release ausgeführt werden, das
dieses Backupformat und Quellschema unterstützt.
Ist ein solcher Pfad nicht belegt, lassen Sie die Instanz gestoppt und nutzen
Sie den [Supportweg](Administration-Verantwortung-Grenzen-und-Support), statt
SQLite oder Migrationstabellen manuell zu verändern.

## Rollback ohne Datenänderung prüfen

Ein Rollback verwendet einen Wartungscontainer des gewünschten älteren
Release-Digests und `lzug-admin` aus exakt demselben älteren Release.
Vorbereitung, Attestation, gestoppter Anwendungscontainer, Volume und
Wartungsgrenze entsprechen dem Upgrade-Ablauf.
Das Zielrelease muss diesen Lifecycle-Vertrag selbst enthalten;
`v0.5.0` und ältere Releases können deshalb nicht per `lzug-admin upgrade rollback`
freigegeben werden.

```sh
./lzug-admin --engine "$ENGINE" --container lzug-maintenance upgrade rollback
```

`rollback` verändert weder Datenbank noch Dokumente.
Der Befehl gibt den älteren Release-Digest nur frei, wenn diese Runtime die
vollständige vorhandene Migrationshistorie kennt und keine Migration aussteht.
Nach `ok: true` darf der Wartungscontainer entfernt, `LZUG_IMAGE` auf genau
diesen geprüften Digest gesetzt und die Referenzinstallation wieder mit
`compose up -d` gestartet werden.

Ein unbekannter neuerer Schemastand oder ein nur vorwärts migrierbarer Stand
wird mit `rollback_not_supported` vor jeder Änderung abgewiesen.
Es gibt keine Rückmigration, kein automatisches Datenrollback und keine
heuristische SQLite-Bearbeitung.

## Exit-Codes und Nachweise

- Exit `0`: Vorgang erfolgreich.
- Exit `29`: irreversible Migration noch nicht ausdrücklich bestätigt.
- Exit `28`: Rollback nicht unterstützt oder Migration fehlgeschlagen.
- Exit `26` oder `27`: Backup ungültig beziehungsweise Empfängerschlüssel
  unbrauchbar oder unpassend.
- Exit `33`: Release-Artefakt, Wartungsgrenze oder Lifecycle-Ausführung nicht
  verifiziert.

Bewahren Sie vorübergehend Zielrelease, Digest, CLI-Build-Metadaten, Zeitfenster,
Backup-Artefaktname und die geheimnisfreie JSON-Antwort auf.
Private Schlüssel, Env-Werte, Pfade und Fachdaten gehören nicht in den
Nachweis.

Der ausführbare technische Vertrag bleibt im Hauptrepository unter
[Betreiber-CLI](https://github.com/lxndrp/lzug/blob/master/docs/developers/components.md#betreiber-cli)
kanonisch.
