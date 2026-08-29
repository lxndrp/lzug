# Öffentliche Azure-Demo

Dieses Verzeichnis beschreibt die isolierte, flüchtige öffentliche Demo aus
[ADR-0015](../../docs/developers/decisions/0015-fluechtige-azure-demo.md). Es
verwaltet mit OpenTofu die Azure-Ressourcen und das GitHub Environment `demo`.
Die konkrete App-/Seed-Assembly folgt zusätzlich
[ADR-0022](../../docs/developers/decisions/0022-tag-gebundene-demo-assembly-und-seed.md).
Der Stack enthält keine Zugangsdaten und führt außerhalb eines ausdrücklich
freigegebenen `tofu apply` keine Cloudänderung aus.

## Sicherheits- und Architekturgrenzen

- `demo_artifact_pair` bindet ausschließlich
  `ghcr.io/lxndrp/lzug-demo-app@sha256:…` und
  `ghcr.io/lxndrp/lzug-demo-seed@sha256:…` zusammen mit Produkt-Tag, Commit,
  dem in beiden Manifesten enthaltenen Runtimevertrag
  `lzug-demo-health-ready-v1`, Schemafingerprint und Seed-Revision. Der
  Seed-Manifest-Digest bindet den Runtimevertrag in die Seed-Revision; die
  beiden Image-Digests binden die jeweiligen Manifeste. Ein einzelner Digest
  wird niemals unabhängig aktualisiert oder zurückgerollt. `latest`, `demo`,
  abweichende Runtimeverträge und andere bewegliche oder nicht nachgewiesene
  Eingaben werden bereits durch die Eingabevalidierung abgewiesen.
- Nicht geheime Laufzeiteinstellungen können über `container_environment`
  übergeben werden. Der Stack akzeptiert keine Secret-Werte; `/data` ist als
  reservierter Runtimepfad nicht überschreibbar.
- Die CORS-Allowlist enthält ausschließlich die exakte Origin
  `https://lzug.repertoire.papaspyrou.name`. `stage.papaspyrou.name`, die
  persönliche `github.io`-Origin und Wildcards werden fail-closed abgewiesen.
  Die verbindliche Demo-Domain ist davon getrennt und lautet
  `https://demo.lzug.repertoire.papaspyrou.name`. Es gibt keine periodischen
  HTTP- oder Uptime-Tests; die Demo kann ohne Nutzungsverkehr auf null
  skalieren.
- Die Container App verwendet Consumption, `min_replicas = 0`, höchstens eine
  Replik, 0,5 vCPU und 1 GiB RAM. Nur der verwaltete HTTPS-Ingress auf den
  internen Anwendungsport ist öffentlich; unverschlüsseltes Ingress und
  zusätzliche Ports sind nicht freigegeben.
- App und generischer Seed-Initializer teilen genau ein replica-scoped
  `EmptyDir`, jeweils ausschließlich unter `/data`. Es gibt keinen Storage
  Account für Anwendungsdaten, kein Azure Files, keine verwaltete Datenbank und
  kein DBaaS. Der Init-Container prüft den Seed und schreibt Datenbank,
  Manifest und Init-/Resetstatus, bevor die App starten darf.
- Eine Consumption Logic App läuft kalenderfest täglich um 03:00 Uhr
  `Europe/Berlin`. Azure bezeichnet dieselbe DST-fähige Zone in der
  Workflowdefinition als `W. Europe Standard Time`. Die Logic App stoppt die
  gesamte Container App, wartet auf `Stopped`, startet dieselbe Single Revision
  und prüft danach `Running`, `/api/health` und `/api/demo/status`.
- Die Logic App besitzt nur eine systemzugewiesene Managed Identity. Eine
  benutzerdefinierte Rolle erlaubt exakt `containerApps/read`,
  `containerApps/stop/action` und `containerApps/start/action`; die Zuweisung
  gilt nur für diese eine Container App. Es existieren weder Controller-Image
  noch Azure-Client-Secret.
- Das Container-Apps-Environment speichert keine Logs dauerhaft und besitzt
  weder einen Log-Analytics-Workspace noch eine Diagnostic-Setting-Route. Bei
  einer konkreten Störung stehen nur begrenzte Echtzeitstreams der App und des
  Environments zur Verfügung; deren kontrollierte Verwendung und der Abgleich
  mit Revision, Digestpaar, Plattformmetriken sowie Deployment-, Reset- und
  Smoke-Nachweisen sind unter
  [Demo-Beobachtbarkeit](../../docs/developers/demo-observability.md)
  dokumentiert. Das Budget meldet 80 Prozent der tatsächlichen und 100 Prozent
  der prognostizierten Kosten; es stoppt Ressourcen nicht automatisch.
- Das GitHub Environment verwendet ausgewählte Deploymentregeln: exakt den
  Branch `master` sowie Tags nach `demo/v*-SNAPSHOT.*` und `v*`. Es verhindert
  Selbstfreigaben und Admin-Bypass. Erforderliche Reviewer werden nicht
  geraten: Sie müssen nach Maintainer-Entscheidung ergänzt werden.
- OIDC-Rollen für Deployment, Auswahl und unabhängige Lieferkettenprüfung des
  freigegebenen Digest-Paars, öffentlicher Smoke-Test und Deploymentnachweis
  sind im [Deploymentvertrag](../../docs/developers/demo-deployment.md)
  beschrieben. Der nächtliche Laufzeitreset ist davon getrennt und benötigt
  weder GitHub Scheduler noch GitHub-Zugang.

## Zustand und Berechtigungen

Produktiver Zustand liegt verschlüsselt und gesperrt in einem bereits
vorhandenen Azure-Blob-Backend. Seine Koordinaten werden aus
`backend.hcl.example` in eine nicht versionierte Datei kopiert. Der State kann
Provider- und Ressourcenmetadaten enthalten und darf deshalb weder committed
noch als öffentliches CI-Artefakt ausgegeben werden. Der State-Storage wird
bewusst außerhalb dieses States gebootstrapped, damit ein `destroy` nicht das
eigene Backend entfernt.

Die lokale Anmeldung erfolgt kurzlebig über Azure CLI und GitHub CLI
beziehungsweise `GITHUB_TOKEN`; CI verwendet später OIDC. Langfristige
Client-Secrets, Storage Keys, SAS-Tokens und Provider-Tokens gehören weder in
`.tfvars` noch in Backenddateien oder Pläne. Für Planung und Anwendung werden
mindestens diese Rechte benötigt:

- Azure: Lesen der Subscription, Erstellen und Verwalten der deklarierten
  Ressourcen in der Demo-Resource-Group sowie Verwalten des zugehörigen
  Resource-Group-Budgets; auf dem State-Container nur Blob-Data-Zugriff.
- GitHub: Verwaltung genau des Environments `demo` und der einen
  Repository-Variable `DEMO_URL` im Repository `lxndrp/lzug`. #126 muss diese
  Rechte von den reinen Deployment-Rechten trennen; das Environment darf keinen
  gleichnamigen `DEMO_URL`-Override enthalten.

Die minimale Runtime-Rolle und ihre Zuweisung sind Teil dieses States. Die
separaten Provisionierungs- und späteren OIDC-Deploymentrechte bleiben davon
getrennt und werden erst nach Maintainer-Freigabe verwendet. Abonnement-ID,
Resource-Group-Namen und E-Mail-Empfänger sind keine Secrets, werden aber für
echte Pläne lokal gehalten. Ein Plan ist wie Betriebsmetadaten zu behandeln
und wird nicht committed.

## Reproduzierbare Prüfung ohne Cloud-Zugriff

OpenTofu 1.12.5 und beide Provider sind fest gepinnt; die Provider-Prüfsummen
liegen in `.terraform.lock.hcl`. Die Repositoryprüfung erstellt ausschließlich
einen gemockten Plan und wendet nichts an:

```sh
task quality:infra
```

Der Test prüft Region, Single Revision und Skalierung, beide Digests, Init-
Container, das explizit erhaltene `Consumption`-Workload-Profil, das einzige
`EmptyDir` unter `/data`, Berliner Zeit, Managed
Identity, die drei RBAC-Aktionen, Stop-/Start-Reihenfolge, getrennte
Liveness-/Readiness-/Statusprüfung, letzten Reset, Rollback-Output, Budget,
den Streaming-only-Loggingvertrag ohne Log-Analytics-, Log-Suchalarm- oder
Diagnostic-Setting-Route sowie die drei ausgewählten GitHub-Environment-
Regeln. Eigene Negativtests verwerfen bewegliche Demo-Tags, alte
Runtimeverträge und eine nur teilweise Policy-Adoption. Das ersetzt keinen
authentifizierten Azure-Plan.

Existieren ausgewählte Environment-Policies bereits außerhalb des States,
werden ihre nicht geheimen numerischen IDs über
`github_environment_deployment_policy_ids = { master = "…", snapshot = "…" }`
übergeben. Nach externer Aktivierung der stabilen Tag-Regel ergänzt die Map
`release = "…"`. `master` und `snapshot` müssen gemeinsam vorhanden sein;
`release` ist bis zu seiner gesondert freigegebenen Anlage optional. Eine leere
Map ist ausschließlich für ein neues Environment ohne bestehende Policies
zulässig, unbekannte oder nur einzelne Bestandspolicies werden fail-closed
abgewiesen.

## Kontrolliertes Erstellen und Aktualisieren

Die folgenden Befehle verändern reale Ressourcen. Sie dürfen erst nach einer
separaten ausdrücklichen Maintainer-Freigabe im Umsetzungstask ausgeführt
werden:

```sh
cd infra/demo
cp terraform.tfvars.example terraform.tfvars
cp backend.hcl.example backend.hcl
# Platzhalter lokal ersetzen, ohne Secrets in Dateien zu schreiben.
tofu init -backend-config=backend.hcl
tofu plan -out=demo.tfplan
tofu show demo.tfplan
tofu apply demo.tfplan
tofu output demo_url
tofu output health_endpoint
tofu output readiness_endpoint
tofu output demo_status_endpoint
tofu output -json deployment
```

Vor `apply` werden Digest, Region, Budget, Empfänger, Backend, erwartete
Ersetzungen und Löschungen im gespeicherten Plan geprüft. Insbesondere müssen
beide Container-Referenzen gemeinsam mit Tag, Commit, Runtimevertrag,
Schemafingerprint und Seed-Revision dem freigegebenen Nachweis entsprechen;
eine unerwartete neue Revision, Persistenzressource, weiter gefasste Rolle oder
zweite Identity ist ein Abbruchgrund. Pläne werden nach der Prüfung lokal
gelöscht und nie hochgeladen oder committed.

## Reset, Fehler und Rollback

Der erfolgreiche geplante Lauf ist in der Logic-App-Laufhistorie sichtbar und
endet erst, wenn alle folgenden Signale erfolgreich sind:

1. Stop-Request mit Managed Identity und Zustand `Stopped`,
2. Start derselben unveränderten Single Revision und Zustand `Running`,
3. erfolgreicher `GET /api/health`,
4. erfolgreicher `GET /api/ready`,
5. erfolgreicher `GET /api/demo/status` mit `initialized = true`, Status
   `ready`, erwarteter Seed-Revision, `Europe/Berlin` und einem höchstens
   15 Minuten alten `last_reset_at`.

Fehlschlagen Stop, Polling, Start, Health oder Statusprüfung, bleibt der Lauf
rot und wird nicht als Resetnachweis gewertet. Bei einem fehlgeschlagenen Start
wird nicht auf eine andere Revision oder einen einzelnen Seed-Digest
ausgewichen. Die Container-App- und Logic-App-Laufhistorie sowie
`GET /api/demo/status` werden gelesen; anschließend wird entweder derselbe Lauf
nach behobener Plattformstörung erneut ausgelöst oder ein Rollback geplant.

Ein Rollback verwendet ausschließlich den vollständigen `artifact_pair`-Output
eines zuvor gemeinsam geprüften Stands. In `terraform.tfvars` werden App- und
Seed-Digest sowie Produkt-Tag, Commit, Runtimevertrag, Schemafingerprint und
Seed-Revision atomar auf dieses Paar zurückgesetzt. Danach folgen ein neuer
gespeicherter Plan, Maintainer-Prüfung und erst nach ausdrücklicher Freigabe
`tofu apply`.
Tags werden nicht verschoben. Der anschließende Stop-/Start-Lauf muss alle vier
obigen Signale erneut liefern. Der bisherige Plan und aktive Stand bleiben bei
einem fehlerhaften neuen Paar unverändert.

## Kontrolliertes Entfernen

Auch die Entfernung benötigt eine eigene Maintainer-Freigabe. Zuerst wird ein
Destroy-Plan geprüft, dann exakt dieser Plan angewendet:

```sh
cd infra/demo
tofu plan -destroy -out=demo-destroy.tfplan
tofu show demo-destroy.tfplan
tofu apply demo-destroy.tfplan
```

Der externe State-Storage bleibt dabei bestehen. Nach erfolgreicher Entfernung
wird geprüft, dass Resource Group, Budget und GitHub Environment entfernt sind;
erst anschließend darf der zugehörige State-Blob nach dem geltenden
Aufbewahrungsprozess gelöscht werden.

## Outputs und Übergabe an #126

- `demo_url`: öffentliche URL der Container App,
- `health_endpoint`: `${demo_url}/api/health`,
- `demo_status_endpoint`: `${demo_url}/api/demo/status`,
- `deployment`: nicht geheime Namen, Environment, Revision-Modus und der
  vollständige unveränderliche Artefaktpaar-/Resetvertrag für Deployment- und
  Rollbacknachweis.

Die URL kann erst nach einem freigegebenen Apply existieren. #126 setzt sie als
Deployment-URL des GitHub Environments und prüft Health, API und Frontend.
