# Azure-Demo deployen

Der manuelle Workflow `Deploy public demo` rollt genau ein zuvor geprüftes,
unveränderliches Demo-Artefaktpaar in die unter
[Demo-Runtime](architecture/demo-runtime.md) beschriebene Azure Container App
aus. Er provisioniert keine Infrastruktur und erzeugt keine Identitäten,
Rollen oder GitHub-Environments.

## Freigabe- und Eingabevertrag

Der Workflow wird ausschließlich von `master` und im geschützten GitHub
Environment `demo` ausgeführt. Ein Maintainer wählt `deploy` oder `rollback`
und übernimmt aus dem erfolgreichen `Demo image pair`-Nachweis des
Publish-Laufs immer alle sechs Werte gemeinsam:

- App-Image `ghcr.io/lxndrp/lzug-demo-app@sha256:…`,
- Seed-Image `ghcr.io/lxndrp/lzug-demo-seed@sha256:…`,
- Produkt-Tag und vollständiger Produkt-Commit,
- Schemafingerprint und Seed-Revision.

Beide OCI-Referenzen werden vor der Azure-Anmeldung gegen die vom Workflow
`.github/workflows/demo-publish.yml` signierten Provenance- und
SBOM-Attestations geprüft. Bewegliche Tags, abweichende Paketnamen,
unvollständige Digests und unvollständige Bindungswerte brechen den Lauf ab.

## Secret-freie GitHub- und Azure-Konfiguration

Das Environment `demo` stellt ausschließlich diese nicht geheimen Variablen
bereit:

| Variable | Inhalt |
| --- | --- |
| `AZURE_CLIENT_ID` | Client-ID der ausschließlich für dieses Deployment verwendeten Entra-Anwendung oder User-Assigned Identity |
| `AZURE_TENANT_ID` | Azure-Tenant-ID |
| `AZURE_SUBSCRIPTION_ID` | Azure-Subscription-ID |
| `AZURE_RESOURCE_GROUP` | Resource Group der Demo |
| `AZURE_CONTAINER_APP` | Name der Demo-Container-App |
| `DEMO_URL` | öffentlicher HTTPS-Origin ohne Pfad, beispielsweise `https://demo.example.org` |

Die statische Site bindet dieselbe öffentliche Demo-URL in ihr geprüftes
Artefakt. Die Container App erlaubt für den Health-Warm-up über
`LZUG_CORS_ALLOWED_ORIGINS` ausschließlich die deklarierte
`landingpage_origin`; standardmäßig ist dies `https://lxndrp.github.io`.

Es existiert kein Client-Secret. Die Federated Credential akzeptiert nur den
GitHub-OIDC-Subject `repo:lxndrp/lzug:environment:demo` und den Audience-Wert
`api://AzureADTokenExchange`. GitHub benötigt für den Job ausschließlich
`contents: read`, `packages: read` und `id-token: write`. `id-token: write`
erlaubt nur das Anfordern des kurzlebigen OIDC-Tokens und gewährt selbst keine
Azure-Berechtigung.

Die Deployment-Identity erhält eine benutzerdefinierte Rolle mit genau diesen
Management-Aktionen:

```text
Microsoft.App/containerApps/read
Microsoft.App/containerApps/write
```

Die Rollenzuweisung gilt ausschließlich für die eine Demo-Container-App, nicht
für Resource Group oder Subscription. Provisionierung, RBAC-Verwaltung,
Stop/Start der Logic App, Logs und State Storage gehören ausdrücklich nicht zu
dieser Rolle. Identity, Federated Credential, Rolle, Environment und Variablen
werden erst nach separater Maintainer-Freigabe außerhalb dieses
Repositoryänderungspakets eingerichtet.

## Ablauf und Nachweis

Der Lauf prüft und dokumentiert folgende getrennte Stufen:

1. secret-freie Eingaben und geschützten `master`-Ref,
2. Provenance und SBOM beider Digests,
3. GitHub-OIDC-Anmeldung an Azure,
4. atomare Änderung beider Images im bestehenden ACA-Revisionstemplate,
5. Azure-Readiness: `Succeeded`, neue erwartete Revision,
   `latestReadyRevisionName == latestRevisionName` und exakt beide Digests,
6. davon getrennt HTTP-Liveness mit `status = ok` und erwartetem Produkt-Commit,
7. davon getrennt Application-Readiness über `/api/ready` mit
   `status = ready` und erwartetem Produkt-Commit,
8. Smoke gegen die unverändert öffentlichen Routen `/api/health`, `/api/ready`,
   `/api/demo/status` und `/`, sowie gegen die geschützte Route
   `/api/openapi.json`. Der anonyme OpenAPI-Aufruf muss exakt `HTTP 401` mit
   der JSON-Antwort `{"error": "Authentication required."}` liefern.

Der Demo-Status muss Produkt-Commit, Schemafingerprint und Seed-Revision des
ausgewählten Paars sowie `initialized = true`, `ready` und `Europe/Berlin`
melden. Erst danach ist der GitHub-Deploymentstatus erfolgreich; die
Environment-Ansicht zeigt denselben Lauf und `DEMO_URL`.

Der geschützte OpenAPI-Smoke schlägt fail-closed fehl, wenn der anonyme Abruf
`HTTP 200`, einen anderen Status, einen anderen Medientyp oder eine abweichende
JSON-Antwort liefert. Er lädt den OpenAPI-Vertrag bewusst nicht ohne
App-Anmeldung und ändert damit die in der
[Sicherheitsbaseline](architecture/security-baseline.md) festgelegte
Authentifizierungsgrenze nicht.

Bei einem Fehler bleibt der Lauf rot und ist kein Deploymentnachweis. Der
Fehlerpfad zeigt ausschließlich nicht geheime ACA-Zustände, Revisionsnamen und
Image-Digests. Er gibt keine Umgebungswerte, Token, vollständigen
Ressourcendokumente oder Logs aus.

## Rollback

Rollback ist niemals ein stiller oder automatischer Wechsel auf einen
einzelnen alten Digest. Ein Maintainer wählt im selben manuellen Workflow
`rollback` und trägt alle sechs Werte eines früheren, gemeinsam geprüften
Paars ein. Danach gelten dieselben Environment-Freigaben, Attestationsprüfungen,
die atomare neue Revision und sämtliche Readiness-/Health-/Smoke-Gates.

Vor einem echten Lauf werden Zielpaar, aktueller Stand, erwartete Revision und
Rückfallpaar durch den Maintainer bestätigt. Ohne die separate Freigabe werden
weder Federated Credential/Rolle/Environment-Variablen eingerichtet noch der
Workflow ausgelöst.

## Lokale und statische Prüfung

Die Deploymentlogik enthält keine Cloud-Mocks im produktiven Pfad. Ihre reinen
Validierungs-, Patch-, Readiness-, Health- und Statusverträge sowie die
Workflow-Sicherheitsgrenzen werden ohne Azure-Zugriff reproduzierbar geprüft:

```sh
task quality:demo-deployment
```

Ein erfolgreicher lokaler Test ersetzt weder die geschützte Environment-
Freigabe noch einen echten Deploymentlauf.

Der Betriebs- und Alarmvertrag ist unter
[Demo-Beobachtbarkeit](demo-observability.md) dokumentiert.

## Referenzen

- [GitHub OIDC für Azure](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure)
- [Azure Container Apps: Revisionen und Readiness](https://learn.microsoft.com/azure/container-apps/revisions)
- [Azure Container Apps Update API](https://learn.microsoft.com/rest/api/resource-manager/containerapps/container-apps/update)
- [GitHub Artifact Attestations prüfen](https://docs.github.com/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
