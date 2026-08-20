# Azure-Demo deployen

Der manuelle Workflow `Deploy public demo` rollt genau ein zuvor geprüftes,
unveränderliches Demo-Artefaktpaar in die unter
[Demo-Runtime](architecture/demo-runtime.md) beschriebene Azure Container App
aus. Er provisioniert keine Infrastruktur und erzeugt keine Identitäten,
Rollen oder GitHub-Environments.

Für einen manuell promoteten Entwicklungs-Snapshot gilt daneben der
zusammenhängende Workflow `Promote demo snapshot`: Ein Maintainer setzt einen
neuen annotierten `demo/...-SNAPSHOT.<kurze SHA>`-Tag auf der aktuellen grünen
`master`-SHA. Der Tag-Push startet den günstigen Source-Preflight,
danach den vollständigen kanonischen `Quality`-Workflow für exakt den
Tag-Zielcommit und erst bei dessen Erfolg Build, separate SBOM- und
Provenance-Attestierung, OCI-Publish sowie unmittelbar denselben OIDC-,
Digestpaar-, Readiness- und Smoke-Vertrag in `demo`. Es gibt für diesen Pfad
weder `workflow_dispatch` noch ein weiteres Required-Reviewer-Gate nach dem
Tag-Push. Branches, Pull Requests, andere Tags und reine Teständerungen lösen
ihn nicht aus.

Vor jeder Tag-Ableitung aktualisiert der Maintainer den Remote-Stand und leitet
SHA, Suffix und Tag ausschließlich aus dem frisch gelesenen `origin/master`
ab:

```sh
git fetch --no-tags origin master
snapshot_sha=$(git rev-parse refs/remotes/origin/master)
test "$(git rev-parse HEAD)" = "$snapshot_sha"
snapshot_short=$(git rev-parse --short=7 "$snapshot_sha")
snapshot_tag="demo/v0.2.0-SNAPSHOT.$snapshot_short"
git tag -a "$snapshot_tag" "$snapshot_sha" -m "Promote $snapshot_tag"
git push origin "refs/tags/$snapshot_tag"
```

Ein fehlgeschlagener Snapshot-Tag bleibt unveränderliche Historie. Er wird
weder lokal noch remote gelöscht, verschoben oder unter demselben Namen erneut
verwendet. Ein weiterer Promotionsversuch beginnt nach einem erneuten Fetch mit
einem neuen aktuellen `master`-Commit und dessen neuem Tag.

Für die einmalige #129-Adoption gilt enger: Der erste neue Snapshot nach Merge
muss Quality, Build, Publish, SBOM, Provenance und die digestgebundenen
App-/Seed-Manifeste erfolgreich abschließen. Sein erwartbarer Deploy-STOP an
der noch nicht adoptierten Readiness-Infrastruktur ist kein Deploymentnachweis
und der Tag wird nicht wiederverwendet. Das veröffentlichte Paar mit
`lzug-demo-health-ready-v1` wird anschließend atomar im neuen, separat
freizugebenden OpenTofu-Plan verwendet. Erst nach dessen Apply beweist ein
weiterer neuer Snapshot mit vollständig grünem automatischem Deploy- und
Smoke-Lauf den Endzustand. Dafür wird weder ein dauerhafter Repository-Marker
noch eine schwächere Snapshot-Pipeline eingeführt.

Der bestehende manuelle Workflow bleibt für releasegebundene Deployments und
den ausdrücklichen Rollback auf ein früher vollständig geprüftes Paar erhalten.

Für ein Deployment verwendet das Environment „Selected branches and tags“ mit
exakt der Branch-Regel `master` für den bestehenden manuellen Deploy-/Rollback-
Pfad und der Tag-Regel `demo/v*-SNAPSHOT.*` für die automatische Snapshot-
Promotion. Ein Required Reviewer ist dort nicht konfiguriert; der annotierte
Tag-Push ist bereits das Maintainer-GO. Der Snapshot-Workflow prüft diese
Aktivierungspolicy erst, nachdem Quality, Build, OCI-Publish, SBOM, Provenance
und das digestgebundene App-/Seed-Manifestpaar erfolgreich belegt sind. Fehlt
oder widerspricht die Policy, stoppt ausschließlich das Deployment vor der
Azure-Anmeldung. Das unveränderliche Paar bleibt damit für die einmalige #129-
Adoption als OpenTofu-Input erhalten, ohne die Deployment-Grenze zu schwächen.

## Freigabe- und Eingabevertrag

Der Workflow wird ausschließlich von `master` und im geschützten GitHub
Environment `demo` ausgeführt. Ein Maintainer wählt `deploy` oder `rollback`
und übernimmt aus dem erfolgreichen `Demo image pair`-Nachweis des
Publish-Laufs immer alle sieben Werte gemeinsam:

- App-Image `ghcr.io/lxndrp/lzug-demo-app@sha256:…`,
- Seed-Image `ghcr.io/lxndrp/lzug-demo-seed@sha256:…`,
- Produkt-Tag und vollständiger Produkt-Commit,
- Runtimevertrag `lzug-demo-health-ready-v1` aus beiden Artefaktmanifesten,
- Schemafingerprint und Seed-Revision.

Beide OCI-Referenzen werden vor der Azure-Anmeldung gegen die vom Workflow
`.github/workflows/demo-publish.yml` oder bei einem Snapshot gegen den Signer
`.github/workflows/demo-snapshot.yml` signierten Provenance- und
SBOM-Attestations geprüft. Anschließend werden beide Digest-Images gelesen und
App- sowie Seed-Manifest vor jeder Azure-Anmeldung gegen Produkt, Runtimevertrag,
Schemafingerprint und Seed-Revision geprüft. Damit kann auch der kontrollierte
manuelle Rollback ein früheres vollständig geprüftes Release- oder
Snapshot-Paar verwenden. Bewegliche Tags, abweichende Paketnamen,
unvollständige Digests, ein alter Health-only-Stand und unvollständige
Bindungswerte brechen den Lauf vor Azure-Mutation ab.

## Secret-freie GitHub- und Azure-Konfiguration

Das Environment `demo` stellt ausschließlich diese nicht geheimen Variablen
bereit:

| Variable                | Inhalt                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| `AZURE_CLIENT_ID`       | Client-ID der ausschließlich für dieses Deployment verwendeten Entra-Anwendung oder User-Assigned Identity |
| `AZURE_TENANT_ID`       | Azure-Tenant-ID                                                                                            |
| `AZURE_SUBSCRIPTION_ID` | Azure-Subscription-ID                                                                                      |
| `AZURE_RESOURCE_GROUP`  | Resource Group der Demo                                                                                    |
| `AZURE_CONTAINER_APP`   | Name der Demo-Container-App                                                                                |
| `DEMO_URL`              | öffentlicher HTTPS-Origin ohne Pfad, beispielsweise `https://demo.example.org`                             |

Die statische Site bindet dieselbe öffentliche Demo-URL in ihr geprüftes
Artefakt. Die Container App erlaubt für den Readiness-Warm-up über
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
`rollback` und trägt alle sieben Werte eines früheren, gemeinsam geprüften
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
