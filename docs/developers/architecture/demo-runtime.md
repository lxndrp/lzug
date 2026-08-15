# Demo-Runtime

Die öffentliche Demo ist eine eigene, flüchtige Assembly und keine
Self-Hosting-Referenz. Ihr technischer Vertrag ist in
[ADR-0022](../decisions/0022-tag-gebundene-demo-assembly-und-seed.md)
festgelegt.

## Artefakte

`Dockerfile.demo` baut die Demo-Anwendung. Sie enthält denselben gemeinsamen
Anwendungscode und dasselbe Schema wie das Produkt des angegebenen Tags, aber
zusätzlich ausschließlich im Demo-Image vorhandene Runtime-Policy- und
Frontend-Provider.

`Dockerfile.demo-seed` baut den vollständig migrierten synthetischen Snapshot.
Der Init-Container prüft dessen Digest und kopiert Datenbank und Manifest in
ein leeres oder zurückzusetzendes `/data`. App- und Seed-Manifest müssen in
Produkt-Tag, Commit und Schemafingerprint übereinstimmen; andernfalls startet
die Demo nicht. Nach erfolgreicher Initialisierung schreibt der Initializer
atomar `demo-runtime-status.json` mit Seed-Revision, `initialized_at` und
`last_reset_at`. Ein fehlender, ungültiger oder zu einem anderen Seed gehöriger
Statusmarker verhindert den App-Start.

Die Assembly akzeptiert zwei strikt getrennte Identitätskanäle:

- Der bestehende releasegebundene Kanal baut aus einem veröffentlichten
  SemVer-Produkt-Tag.
- Der Snapshot-Kanal baut ausschließlich aus einem annotierten Tag der Form
  `demo/vMAJOR.MINOR.PATCH-SNAPSHOT.<kurze SHA>`. Seine sichtbare Identität ist
  beispielsweise `v0.2.0-SNAPSHOT@16a87c5`, sein Metadatenfeld `release`
  bleibt `false`, und er ist weder Produkt-Release noch Self-Hosting-Artefakt.

App- und Seed-Manifest binden in beiden Kanälen denselben Kanal, Tag,
Zielversion, sichtbare Identität, vollständigen Commit und Schemafingerprint.
Der Seed ergänzt seine inhaltsadressierte Revision. Die Promotion- und
Deploymentgrenzen des Snapshot-Kanals beschreibt
[ADR-0024](../decisions/0024-manuell-promotete-demo-snapshots.md).

Lokale Entwicklung darf einen expliziten Test-Tag verwenden:

```bash
revision=$(git rev-parse HEAD)
version=$(PRODUCT_TAG=v0.1.1 PRODUCT_COMMIT="$revision" python3 -c \
  'import os; from backend.build_metadata import BuildMetadata; print(BuildMetadata.create(os.environ["PRODUCT_COMMIT"], os.environ["PRODUCT_TAG"]).identity)')
docker build -f Dockerfile.demo-seed \
  --build-arg PRODUCT_TAG=v0.1.1 --build-arg VCS_REF="$revision" \
  -t lzug-demo-seed:local .
docker build -f Dockerfile.demo \
  --build-arg BUILD_IDENTITY="$version" --build-arg PRODUCT_TAG=v0.1.1 \
  --build-arg VCS_REF="$revision" -t lzug-demo-app:local .
scripts/demo-container-smoke.sh lzug-demo-app:local lzug-demo-seed:local
```

## Öffentliche Schnittstellen

- `GET /api/demo/status` nennt Produktversion und Commit, Seed-Revision,
  Schemafingerprint, Initialisierungszeit, letzten und nächsten Reset, aber
  keine Geheimnisse.
- `POST /api/demo/session` akzeptiert ausschließlich `chair` oder `examiner`
  und erzeugt eine zufällige Sitzung mit 60 Minuten Laufzeit.
- `GET /api/session` ergänzt in der Demo Anzeigename, Rolle und Capabilities.
- `/api/health` bleibt der minimale allgemeine Liveness-Vertrag; `/api/ready`
  signalisiert davon getrennt die vollständig initialisierte Demo.

Die statische Landingpage ruft ausschließlich den Readiness-Vertrag auf. Die
Demo-Runtime setzt dafür `LZUG_CORS_ALLOWED_ORIGINS` auf die exakte
GitHub-Pages-Origin `https://lxndrp.github.io`; der Projektpfad `/lzug` gehört
nicht zu einer Origin. Wildcards und weitere Origins bleiben ausgeschlossen.
Der Browseraufruf überträgt weder Cookies noch Referrer und leitet erst bei
`status = ready` zur Demo weiter.

Die Rollenwahl ersetzt nur in dieser Assembly die lokale Anmeldung. Einladung,
Recovery und Betreiberzugänge sind nicht öffentlich erreichbar. Sämtliche
Mutationen durchlaufen zusätzlich zur normalen Ausschussautorisierung die
Default-Deny-Allowlist der Demo.

## Reset und Betrieb

Die Anwendung verwendet ausschließlich das gemeinsam mit dem Init-Container
gemountete `EmptyDir`. Die öffentliche Azure-Demo wird täglich um 03:00 Uhr
`Europe/Berlin` vollständig gestoppt und wieder gestartet. Erst der Start mit
frischem Volume und erneutem Seed-Init gilt als Reset; Scale-to-zero oder ein
Containerneustart allein reichen nicht als Löschbeweis.

Während des Resets ist die Demo kurzzeitig nicht erreichbar. Alte Sessions
und sämtliche während der Nutzung erzeugten Daten verlieren danach ihre
Gültigkeit. Die Oberfläche weist dauerhaft auf diese Grenze und das Verbot
realer personenbezogener Daten hin. Die konkrete Azure-Assembly, die minimale
Runtime-Rolle sowie Fehler- und Rollbackabläufe sind in
`infra/demo/README.md` dokumentiert.
