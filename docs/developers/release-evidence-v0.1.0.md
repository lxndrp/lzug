# Release- und Betriebsnachweise für `v0.1.0`

## Geltungsbereich

Diese Seite bündelt die reviewbaren Nachweise für den technischen
`v0.1.0`-Umfang. Die Version liefert reproduzierbare Versions-, Qualitäts- und
Release-Infrastruktur. Sie beansprucht weder fachliche Vollständigkeit noch
Produktionsreife, einen unterstützten Self-Hosting-Betrieb oder einen realen
Pilot.

Der verworfene Kandidat
`ede48e41af93102f31e9d3bcc746d5b30bd7be90` bleibt unverändert. Diese
Dokumentation wird erst über einen regulären Pull Request Bestandteil eines
neuen `master`-Commits und kann danach einen neuen unveränderlichen Kandidaten
begründen.

## Ressourcenvertrag

| Ressource | Belastbarer Nachweis für `v0.1.0` | Bewusste Grenze |
| --- | --- | --- |
| CPU | Container- und Compose-Smokes starten einen einzelnen Anwendungscontainer und prüfen Health, API, SPA, Authentifizierungsisolation und Persistenz ohne CPU-Limit. | Es gibt keinen Last-, Durchsatz- oder Drosseltest und daher keine unterstützte quantitative Mindest- oder Referenz-CPU. |
| RAM | Dieselben Smokes prüfen Start und Kernverträge ohne gesetztes Speicherlimit. | Es gibt keinen Speicherlimit-, Last- oder Maximaldatentest und daher keine unterstützte quantitative Mindest- oder Referenz-RAM-Größe. |
| Persistenter Storage | `backend.database.DEFAULT_MIN_FREE_BYTES` erzwingt beim Start mindestens 64 MiB freien Speicher auf jedem eindeutigen Dateisystem für Daten, Datenbank, Dokumente und Migrationsschutzkopien. Unit-Tests prüfen den positiven und negativen Vertrag; der Compose-Smoke prüft `/data` über Neustart und Stop/Start. | 64 MiB sind nur die fail-closed Startschwelle, keine Kapazitäts- oder Aufbewahrungsempfehlung. Datenmenge, Dokumente, WAL-Dateien und Schutzkopien erfordern zusätzlichen, betreiberspezifisch geplanten Speicher. |

CPU und RAM müssen für die konkrete Umgebung vor einem nicht beanspruchten
produktiven Einsatz gemessen und festgelegt werden. Konkrete Zahlen ohne diese
Messungen wären Scheinpräzision. Unterstützte Betriebsanforderungen gehören zum
Self-Hosting-Umfang von `v0.6.0`.

## Laufzeit- und Persistenzkonsistenz

- Der Container läuft als UID/GID `10001:10001`, mit read-only Root-Dateisystem,
  flüchtigem `/tmp`, ohne Capabilities und standardmäßig nur hinter einem
  Loopback-Port. Ein Bind-Mount muss für diese UID/GID beschreibbar sein.
- `/data/lzug.sqlite`, `/data/documents` und `/data/backups` bilden den
  persistenten Vertrag. SQLite-WAL benötigt zusätzlich Schreibzugriff für
  `-wal` und `-shm` neben der Datenbank.
- Ohne `LZUG_AUTH_ENCRYPTION_KEY` wird ein Schlüssel mit Modus `0600` unter
  `/data` erzeugt. Er gehört zum Datenbestand und darf weder im Image noch in
  Repository- oder Compose-Konfiguration abgelegt werden.
- Der Healthcheck meldet nur bei erreichbarer Datenbank, konsistentem
  Migrationsstand, beschreibbaren Pfaden und ausreichendem freien Speicher
  HTTP 200. `docker compose ps`, Container-Logs und
  `python -m backend.healthcheck` bilden den dokumentierten Diagnosepfad.
- Container- und Compose-Smokes prüfen Non-Root-Betrieb, Health, Neustart,
  Stop/Start und `/data`-Persistenz. Sie prüfen keinen allgemeinen
  Backup-/Restore- oder Produkt-Rollback-Pfad.

Die Details stehen in der [OCI-Runtime](architecture/oci-runtime.md), der
[Compose-Referenz](architecture/compose-self-hosting.md) und der
[Datenbankschema-Referenz](database-schema.md).

## Upgrade, Backup, Restore und Rollback

`v0.1.0` ist der erste geplante Release und besitzt keinen unterstützten
Vorgänger. Es wird deshalb kein Upgradepfad beansprucht. Automatische
Migrationsschutzkopien schützen einen einzelnen Migrationsschritt, sind aber
keine allgemeine Backup-, Restore- oder Exportfunktion.

Für `v0.1.0` werden allgemeines Backup, Restore und Produkt-Rollback ausdrücklich
nicht unterstützt. Ein älteres Image zurückzuschalten rollt weder Datenbank
noch Dokumente oder Authentifizierungszustand sicher zurück. Diese Pfade sind
für `v0.6.0` geplant und müssen vor einem entsprechenden Betriebsversprechen
mit Integritätsprüfung getestet werden.

Davon getrennt ist das
[Fehler- und Wiederanlaufverhalten des Release-Workflows](releases.md#fehler-und-wiederanlaufverhalten):
Ein Teilfehler kann einen unveränderlichen Registry-Inhalt oder Draft
hinterlassen, veröffentlicht aber keinen vollständigen GitHub Release. Der
Workflow öffnet das Gate wieder und darf denselben exakt gebundenen Draft oder
Tag erneut verwenden. Dieses Release-Recovery verändert keine Instanzdaten und
ist kein Produkt-Rollback.

## Lizenz, Datenschutz und Pilot

- `task sbom` erzeugt mit der gepinnten Syft-Version die kanonische
  CycloneDX-Dependency-SBOM aus der installierten locked Python-Umgebung,
  `frontend/package-lock.json` und `go.mod`. Fehlende oder mehrdeutige
  Lizenzmetadaten bleiben sichtbar und erfordern menschliche Prüfung. Die SBOM
  ist keine Rechtsberatung.
- `task sbom:cli` stellt für #273 denselben Syft-/CycloneDX-Vertrag pro bereits
  gebautem nativen Binary bereit. #328 veröffentlicht keine CLI-Artefakte;
  Buildmatrix, Manifest, Checksums und Attestations bleiben Bestandteil von
  #273 auf dem kritischen Pfad `#328 → #273 → #325`.
- Projektcode ist `AGPL-3.0-or-later`; originale Dokumentationsprosa ist nach
  der in [`docs/LICENSE.md`](../LICENSE.md) festgelegten Grenze `CC-BY-4.0`.
  Drittmaterial behält seine eigene Lizenz.
- Die [Datenschutzabgrenzung](privacy.md) bezieht sich ausschließlich auf
  Repository-, CI- und Release-Metadaten. Reale Betriebsdaten und eine
  produktive Datenschutzabnahme werden nicht beansprucht.
- Ein veröffentlichter RC oder realer Pilot ist für `v0.1.0` nicht vorgesehen.
  Die integrierte Wintererprobung ist `v1.0.0-rc.1` zugeordnet.

Der Release-Workflow ergänzt bei einer späteren tatsächlichen Veröffentlichung
den konkreten GHCR-Digest, Image- und Dependency-SBOM, Provenance,
Attestations, Prüfsummen und Lauf-Links. Diese dynamischen Nachweise werden
nicht vorab erfunden oder als bereits vorhanden dargestellt.
