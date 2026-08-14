# Öffentliche Azure-Demo

Dieses Verzeichnis beschreibt die isolierte, flüchtige öffentliche Demo aus
[ADR-0015](../../docs/developers/decisions/0015-fluechtige-azure-demo.md). Es
verwaltet mit OpenTofu die Azure-Ressourcen und das GitHub Environment `demo`.
Es führt selbst kein Deployment aus und enthält keine Zugangsdaten.

## Sicherheits- und Architekturgrenzen

- `image_reference` akzeptiert ausschließlich ein Paket unter
  `ghcr.io/lxndrp/…@sha256:<digest>`. Paketname, getrenntes Demo-Artefakt und
  Seed-Vertrag entscheidet #124. Nicht geheime Laufzeiteinstellungen können
  später über `container_environment` übergeben werden; Secret-Werte werden
  von diesem Stack bewusst nicht angenommen. Diese Konfiguration nimmt die
  Entscheidung nicht vorweg.
- Die Container App verwendet Consumption, `min_replicas = 0`, höchstens eine
  Replik, 0,5 vCPU und 1 GiB RAM. Nur der verwaltete HTTPS-Ingress auf den
  internen Anwendungsport ist öffentlich; unverschlüsseltes Ingress und
  zusätzliche Ports sind nicht freigegeben.
- Es gibt weder Volume noch Volume-Mount, Storage Account für Anwendungsdaten,
  verwaltete Datenbank oder DBaaS. Das beschreibbare Container-Dateisystem ist
  flüchtig. Das aus #124 hervorgehende Demo-Image muss die vorbereiteten Daten
  beim Start in dieses flüchtige Dateisystem kopieren.
- Log Analytics bewahrt Logs 30 Tage auf und begrenzt die tägliche Aufnahme
  auf 0,5 GB. Ein monatliches Resource-Group-Budget meldet 80 Prozent der
  tatsächlichen Kosten und 100 Prozent der prognostizierten Kosten. Azure
  Budgets alarmieren; sie stoppen Ressourcen nicht automatisch.
- Das GitHub Environment erlaubt Deployments nur von geschützten Branches,
  verhindert Selbstfreigaben und Admin-Bypass. Erforderliche Reviewer werden
  nicht geraten: Sie müssen nach Maintainer-Entscheidung ergänzt werden.
- OIDC-Rollen, Auswahl des freigegebenen Digests, Deployment, Health-Warten,
  Smoke-Test und Rollback gehören zu #126. Bis dahin wird kein produktiver
  Deployment-Workflow angelegt.

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
- GitHub: Verwaltung genau des Environments `demo` im Repository `lxndrp/lzug`.
  #126 muss diese Rechte von den reinen Deployment-Rechten trennen.

Konkrete Rollen und Federated Credentials werden erst mit #126 und nach
Maintainer-Freigabe eingerichtet. Abonnement-ID, Resource-Group-Namen und
E-Mail-Empfänger sind keine Secrets, werden aber für echte Pläne lokal
gehalten. Ein Plan ist wie Betriebsmetadaten zu behandeln und wird nicht
committed.

## Reproduzierbare Prüfung ohne Cloud-Zugriff

OpenTofu 1.12.5 und beide Provider sind fest gepinnt; die Provider-Prüfsummen
liegen in `.terraform.lock.hcl`. Die Repositoryprüfung erstellt ausschließlich
einen gemockten Plan und wendet nichts an:

```sh
task quality:infra
```

Der Test prüft Region, Skalierung, Limits, Digest, fehlende Volumes, HTTPS-
Ingress, Budget und GitHub Environment. Er ersetzt keinen authentifizierten
Azure-Plan.

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
tofu output -json deployment
```

Vor `apply` werden Digest, Region, Budget, Empfänger, Backend, erwartete
Ersetzungen und Löschungen im gespeicherten Plan geprüft. Ein Update verwendet
denselben Ablauf mit neuem Digest oder explizit geänderten Eingaben. Pläne
werden nach der Prüfung lokal gelöscht und nie hochgeladen oder committed.

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
- `deployment`: nicht geheime Namen, Environment, Revision-Modus und der
  unveränderliche Image-Digest für den späteren Deployment-Nachweis.

Die URL kann erst nach einem freigegebenen Apply existieren. #126 setzt sie als
Deployment-URL des GitHub Environments und prüft Health, API und Frontend.
