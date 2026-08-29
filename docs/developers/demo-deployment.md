# Azure-Demo deployen

Jedes veröffentlichte stabile SemVer-Release ruft im selben Releaseworkflow
den wiederverwendbaren Pfad `Promote stable release to public demo` auf.
Dieser veröffentlicht oder verifiziert das unveränderliche Demo-App-/Seed-Paar
und verwendet anschließend denselben Workflow `Deploy public demo`, der auch
für Snapshots sowie den manuellen Deploy und Rollback zuständig ist. Ein
Release Candidate überspringt die Demo-Promotion. Ein Fehler der nachgelagerten
Promotion verändert den bereits veröffentlichten Produktrelease nicht.

Die Verkettung verwendet `workflow_call`. Sie wartet nicht auf ein durch das
repositoryeigene `GITHUB_TOKEN` erzeugtes `release: published`-Ereignis und
benötigt weder PAT noch GitHub App. Der Deploymentworkflow provisioniert keine
Infrastruktur und erzeugt keine Identitäten, Rollen oder GitHub-Environments.

Für einen manuell promoteten Entwicklungs-Snapshot gilt daneben der
zusammenhängende Workflow `Promote demo snapshot`: Ein Maintainer setzt einen
neuen annotierten `demo/...-SNAPSHOT.<kurze SHA>`-Tag auf der aktuellen grünen
`master`-SHA. Der Tag-Push startet den günstigen Source-Preflight und akzeptiert
nur einen bereits erfolgreichen vollständigen `Quality`-Workflow für exakt
dieselbe aktuelle `master`-SHA. Erst danach folgen Build, separate SBOM- und
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
der Branch-Regel `master`, der Snapshot-Regel `demo/v*-SNAPSHOT.*` und der
vorbereiteten stabilen Tag-Regel `v*`. Ein Required Reviewer ist dort nicht
konfiguriert; die einzige menschliche Freigabe eines stabilen Produktpfads
bleibt das Environment `release`. Die Regeln werden deklarativ durch OpenTofu
verwaltet und vom Runner nicht über die GitHub-API nachgeprüft. Ihre reale
Aktivierung bleibt eine gesondert freizugebende externe Änderung.

## Freigabe- und Eingabevertrag

Der wiederverwendbare Workflow läuft im geschützten GitHub Environment `demo`.
Der stabile Pfad wird von `master`, der Snapshotpfad vom unveränderlichen
Snapshot-Tag aufgerufen. Beim manuellen Pfad wählt ein Maintainer auf `master`
`deploy` oder `rollback` und übernimmt immer alle sieben Werte gemeinsam:

- App-Image `ghcr.io/lxndrp/lzug-demo-app@sha256:…`,
- Seed-Image `ghcr.io/lxndrp/lzug-demo-seed@sha256:…`,
- Produkt-Tag und vollständiger Produkt-Commit,
- Runtimevertrag `lzug-demo-health-ready-v1` aus beiden Artefaktmanifesten,
- Schemafingerprint und Seed-Revision.

Beide OCI-Referenzen werden vor der Azure-Anmeldung gegen die vom Workflow
`.github/workflows/demo-publish.yml` oder bei einem Snapshot gegen den Signer
`.github/workflows/demo-snapshot.yml` signierten Provenance-Attestations
geprüft. Die weiterhin erzeugten SBOM-Attestierungen sind Liefer- und
Inventarnachweise, aber kein zweites Deployment-Gate. Anschließend werden beide Digest-Images gelesen und
App- sowie Seed-Manifest vor jeder Azure-Anmeldung gegen Produkt, Runtimevertrag,
Schemafingerprint und Seed-Revision geprüft. Damit kann auch der kontrollierte
manuelle Rollback ein früheres vollständig geprüftes Release- oder
Snapshot-Paar verwenden. Bewegliche Tags, abweichende Paketnamen,
unvollständige Digests, ein alter Health-only-Stand und unvollständige
Bindungswerte brechen den Lauf vor Azure-Mutation ab.

## Kanonischer Vertragskern

`demo/contract.py` ist die stabile, reine CLI- und Python-Grenze für alle
fachlichen Demo-Lieferregeln. Snapshot-, Publish-, Promotions-, Deploy- und
manueller Rollbackpfad rufen sie mit `python3 -m demo.contract` auf. Die
Workflows transportieren die geprüften Werte und orchestrieren externe
GitHub-, Registry- und Azure-Schritte, bilden die Regeln aber nicht erneut mit
regulären Ausdrücken oder `jq`-Prädikaten nach.

| Regel | Kanonische Implementierung |
| --- | --- |
| Release-, stabile Release- und Snapshotidentität einschließlich Tag-/Commit-Bindung | `demo.identity.DemoIdentity`, aufgerufen über `demo.contract.demo_identity` und den CLI-Befehl `identity` |
| Manifestversion, Produktidentität, Runtimevertrag, Schemafingerprint und Seed-Revision | `demo.contract.validate_manifest` und `validate_manifest_pair`; `demo.artifacts` ergänzt nur Datei-, Datenbank- und Build-Prüfungen |
| Unveränderliche App-/Seed-Digestreferenzen und vollständiges Sieben-Werte-Paar | `demo.contract.DemoArtifactPair` |
| Automatischer Aufrufkanal sowie manueller Deploy/Rollback auf `master` | `demo.contract.validate_deployment_source` |
| Allgemeine öffentliche HTTPS-Origin und verbindliche Repository-Demo-Origin | `demo.contract.validate_public_demo_url` |

Bewusste technische Ausnahmen bleiben dort, wo externe Evidenz erforderlich
ist: Annotiertheit und Unveränderlichkeit eines Git-Tags, aktuelle
`master`-SHA, erfolgreiche Quality-Läufe, OCI-Provenance, GitHub-OIDC,
Azure-Revision, Readiness und finaler Smoke-Test werden von den zuständigen
Werkzeugen und Workflows geprüft. Die Skripte `scripts/demo_snapshot.py`,
`scripts/validate_demo_url_contract.py` und der Befehl `validate-inputs` in
`scripts/demo_deployment.py` bleiben als kompatible Adapter bestehen und
delegieren ohne eigene fachliche Regeln an den Vertragskern.

## Secret-freie GitHub- und Azure-Konfiguration

Das geschützte Environment `demo` stellt ausschließlich die Azure-Koordinaten
für den Deploymentjob bereit:

| Variable                | Inhalt                                                                                                     |
| ----------------------- | ---------------------------------------------------------------------------------------------------------- |
| `AZURE_CLIENT_ID`       | Client-ID der ausschließlich für dieses Deployment verwendeten Entra-Anwendung oder User-Assigned Identity |
| `AZURE_TENANT_ID`       | Azure-Tenant-ID                                                                                            |
| `AZURE_SUBSCRIPTION_ID` | Azure-Subscription-ID                                                                                      |
| `AZURE_RESOURCE_GROUP`  | Resource Group der Demo                                                                                    |
| `AZURE_CONTAINER_APP`   | Name der Demo-Container-App                                                                                |

`DEMO_URL` gehört nicht in das Environment. Es existiert genau einmal als
nicht-sensitive Repository-Variable und hat verbindlich den Wert
`https://demo.lzug.repertoire.papaspyrou.name`. Publication und beide Demo-
Deploymentpfade lassen GitHub Actions diese Repository-Variable über
`vars.DEMO_URL` zum effektiven Workflowwert auflösen und validieren diesen ohne
erneuten API-Zugriff. Ein fehlender Repository-Wert, der Placeholder
`https://demo.example.invalid` oder ein anderer Origin lässt den jeweiligen
echten Pfad vor Veröffentlichung beziehungsweise Azure-Anmeldung fail-closed
scheitern. Das geschützte Environment `demo` darf weiterhin keinen
gleichnamigen Override enthalten; dieser Konfigurationsvertrag wird außerhalb
des Runners am jeweiligen Aktivierungsgate geprüft. PR-/Push-Buildprüfungen der
Publication dürfen den Placeholder weiterhin ausschließlich als sichere lokale
Testeingabe verwenden.

Die statische Site bindet dieselbe öffentliche Demo-URL in ihr geprüftes
Artefakt. Die Container App erlaubt für den Readiness-Warm-up über
`LZUG_CORS_ALLOWED_ORIGINS` ausschließlich die deklarierte
`landingpage_origin`; verbindlich ist dies `https://lzug.repertoire.papaspyrou.name`.

Der Azure-Standard-FQDN wird nie als dauerhaftes Produktziel übernommen. Die
bestätigte Domainhierarchie, DNS-, Zertifikats- und Betreiber-Gates stehen in
der [Betriebsanleitung für öffentliche Domains](publication-domains.md).

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

1. secret-freie Eingaben und den zum Kanal passenden unveränderlichen Ref,
2. Provenance beider Digests und den gemeinsamen Manifestvertrag,
3. GitHub-OIDC-Anmeldung an Azure,
4. atomare Änderung beider Images im bestehenden ACA-Revisionstemplate,
5. Azure-Readiness: `Succeeded`, neue erwartete Revision,
   `latestReadyRevisionName == latestRevisionName` und exakt beide Digests,
6. davon getrennt Application-Readiness über `/api/ready` mit
   `status = ready` und erwartetem Produkt-Commit,
7. abschließender Smoke gegen die unverändert öffentlichen Routen `/api/health`, `/api/ready`,
   `/api/demo/status` und `/`, sowie gegen die geschützte Route
   `/api/openapi.json`. Der anonyme OpenAPI-Aufruf muss exakt `HTTP 401` mit
   der JSON-Antwort `{"error": "Authentication required."}` liefern.

Der Demo-Status muss Produkt-Commit, Schemafingerprint und Seed-Revision des
ausgewählten Paars sowie `initialized = true`, `ready` und `Europe/Berlin`
melden. Erst danach ist der GitHub-Deploymentstatus erfolgreich; die
Environment-Ansicht zeigt denselben Lauf, während `DEMO_URL` weiterhin aus
der Repository-Konfiguration stammt.

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
Validierungs-, Patch-, Readiness- und Statusverträge sowie die
Workflow-Sicherheitsgrenzen werden ohne Azure-Zugriff reproduzierbar geprüft:

```sh
task quality:demo-deployment
```

Ein erfolgreicher lokaler Test ersetzt weder die geschützte Environment-
Freigabe noch einen echten Deploymentlauf.

Der Betriebs- und Alarmvertrag ist unter
[Demo-Beobachtbarkeit](demo-observability.md) dokumentiert.

## Referenzen

- [ADR-0026: Automatische Demo-Promotion stabiler Releases](decisions/0026-automatische-demo-promotion-stabiler-releases.md)
- [GitHub OIDC für Azure](https://docs.github.com/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure)
- [Azure Container Apps: Revisionen und Readiness](https://learn.microsoft.com/azure/container-apps/revisions)
- [Azure Container Apps Update API](https://learn.microsoft.com/rest/api/resource-manager/containerapps/container-apps/update)
- [GitHub Artifact Attestations prüfen](https://docs.github.com/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
