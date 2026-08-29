# Öffentliche Demo betreiben

Die öffentliche Demo ist eine flüchtige, von Self-Hosting getrennte Assembly.
Die ausführbaren Verträge liegen in `demo/`, den Dockerfiles,
`.github/workflows/demo-*.yml` und `infra/demo/`; dieses Runbook beschreibt
nur den aktuellen sicheren Ablauf. Infrastruktur, Identitäten, GitHub
Environments und Repository-Variablen werden nicht manuell aus dieser Seite
nachgebaut.

## Voraussetzungen

- Die Demo verwendet ein unveränderliches App-/Seed-Digestpaar mit gemeinsamem
  Produkt-Tag, Commit, Runtimevertrag, Schemafingerprint und Seed-Revision.
- Die bereitstellenden Artefakte besitzen die erwartete Provenance. Bewegliche
  Tags, Teilpaare und abweichende Manifeste sind keine Eingabe.
- Der manuelle Workflow läuft auf `master` im geschützten Environment `demo`.
  Eine Azure-Änderung, einschließlich eines Rollbacks, benötigt ein separates
  Maintainer-GO.

Die Anwendung nutzt nur ein flüchtiges Datenvolume. Ein täglicher Reset startet
sie mit dem synthetischen Seed neu. `/api/health` ist Liveness;
`/api/ready` bestätigt die initialisierte Anwendung. Die Landingpage leitet
erst nach erfolgreicher Readiness weiter. Die öffentliche URL und CORS-Origin
werden durch die ausführbaren Verträge fail-closed geprüft.

Die Landingpage verwendet `https://lzug.repertoire.papaspyrou.name`, die Demo
`https://demo.lzug.repertoire.papaspyrou.name`. `DEMO_URL` ist die einzige
nicht-sensitive Repository-Variable für die Demo-Origin und darf im Environment
`demo` nicht überschrieben werden. DNS, Zertifikate, Pages- oder Azure-Custom-
Domain-Änderungen sind externe Betriebsvorgänge und nicht Bestandteil dieses
Runbooks.

## Release, Snapshot und manueller Betrieb

Ein stabiles Produktrelease ruft nach seiner Veröffentlichung automatisch die
Demo-Promotion auf. Release Candidates überspringen sie. Für einen
Entwicklungs-Snapshot erzeugt ein Maintainer nach erfolgreichem vollständigem
`Quality`-Lauf auf dem aktuellen `master` einen neuen annotierten Tag:

```sh
git fetch --no-tags origin master
snapshot_sha=$(git rev-parse refs/remotes/origin/master)
snapshot_short=$(git rev-parse --short=7 "$snapshot_sha")
snapshot_tag="demo/v0.2.0-SNAPSHOT.$snapshot_short"
git tag -a "$snapshot_tag" "$snapshot_sha" -m "Promote $snapshot_tag"
git push origin "refs/tags/$snapshot_tag"
```

Der Tag bleibt unveränderlich. Bei einem fehlgeschlagenen Lauf beginnt ein
neuer Versuch mit einem neu gelesenen `master`-Commit und einem neuen Tag.

Für einen ausdrücklich freigegebenen manuellen Deploy oder Rollback wird
`Deploy public demo` auf `master` gestartet. Der Maintainer übergibt das
vollständige, bereits geprüfte Sieben-Werte-Paar; der Workflow prüft Quelle,
Digests, Provenance und Manifeste vor der Azure-Anmeldung. Ein Rollback wählt
immer ein vollständiges früheres Paar, nie nur ein einzelnes Image.

## Erwarteter Nachweis und Diagnose

Ein erfolgreicher Lauf bestätigt die atomare Revision mit beiden Digests,
Application-Readiness und den öffentlichen Smoke. Der Status nennt den
Produkt-Commit, Schemafingerprint und die Seed-Revision; Logs bleiben auf
strukturierte, datensparsame Ereignisse und begrenzte Echtzeitdiagnose
beschränkt. Das verbindliche Kostenlimit und der read-only-Abgleich stehen in
der [Demo-Kostenbaseline](demo-cost-baseline.md).

Der Smoke prüft `/api/health`, `/api/ready`, `/api/demo/status` und die
Landingpage. Die geschützte Route `/api/openapi.json` bleibt anonym bei
`HTTP 401` mit `{"error": "Authentication required."}`; sie wird nicht zum
Laden eines öffentlichen API-Vertrags geöffnet.

Bei einem Fehler bleibt der Lauf rot. Zuerst sind Workflow-Zusammenfassung,
Revision, Digestpaar und die drei Readiness-Signale zu prüfen. Keine Tokens,
Environmentwerte oder vollständigen Ressourcenantworten veröffentlichen. Ein
fehlgeschlagener Deploy wird nicht durch eine ungeprüfte Wiederholung oder
einen einzelnen Imagewechsel korrigiert; für ein notwendiges Zurücksetzen gilt
der explizite Rollbackpfad mit neuem Maintainer-GO.

## Lokale Prüfung

```sh
task quality:demo-deployment
task quality:infra
```

Die erste Prüfung deckt Liefer-, Workflow- und Deploymentverträge ohne
Cloudzugriff ab; die zweite validiert das OpenTofu-Modul mit einem Mock-Plan.
Beide ersetzen weder eine Environment-Freigabe noch einen echten Lauf.

## Referenzen

- [ADR-0022: Tag-gebundene Demo-Assembly](decisions/0022-tag-gebundene-demo-assembly-und-seed.md)
- [ADR-0024: Manuell promotete Demo-Snapshots](decisions/0024-manuell-promotete-demo-snapshots.md)
- [ADR-0026: Automatische Demo-Promotion](decisions/0026-automatische-demo-promotion-stabiler-releases.md)
