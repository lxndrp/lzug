# Beobachtbarkeit der öffentlichen Demo

Die öffentliche Demo verwendet eine kleine, datenschutzgerechte
Betriebsbaseline. Der Repositoryvertrag ist reproduzierbar; reale Azure-,
Budget-, Alert-, Environment- und Monitoringänderungen benötigen weiterhin
ein separates Maintainer-GO. Eine öffentliche Statusseite gehört ausdrücklich
nicht zu diesem Umfang.

## Getrennte Betriebssignale

- `GET /api/health` ist reine Prozess-Liveness. Die Antwort ist unabhängig von
  Datenbankzugriffen und enthält nur `status = ok`, Produktversion,
  Quellrevision und den Self-Link.
- `GET /api/ready` ist Application-Readiness. Erst eine vollständig
  initialisierte und migrierte Datenbank ergibt HTTP 200 und `status = ready`;
  andernfalls folgen HTTP 503 und `status = unavailable`.
- Azure Container Apps verwendet `/api/health` für Liveness und `/api/ready`
  für Readiness. Deployment-Smoke und Reset prüfen beide Signale getrennt.

Die statische Landingpage aus #127 darf nach der Trennung nicht mehr anhand
von `/api/health` weiterleiten. Ihr interaktiver Warm-up nach einem bewussten
Klick und der zugehörige Browservertrag müssen `/api/ready` verwenden. #127
ist deshalb ein nativer Blocker für die Aktivierung dieses Pakets.

## Strukturierte, datensparsame Logs

Die Anwendung schreibt je Ereignis genau ein kompaktes JSON-Objekt nach
`stdout`. Zulässig sind nur feste Ereignis- und Feldnamen sowie skalare,
gebundene Werte. Jeder Eintrag enthält `deployment_digest`; OpenTofu setzt ihn
auf den unveränderlichen `sha256:…`-Digest des App-Images, und der
Deploymentworkflow aktualisiert ihn atomar mit dem Imagepaar.

HTTP-Logs enthalten Methode, normalisierte Routenschablone, Status und
Byteanzahl. Queryparameter, Client-IP, Header, Cookies, Request- und
Response-Bodies, Namen, E-Mail-Adressen, Tokens, Passwörter und Stacktraces
werden nicht aufgenommen. Unbekannte API-Segmente werden als `unknown`, IDs
als `:id` und statische Pfade gemeinsam als `/static` erfasst.

Frontendfehler werden ohne Meldung, Stack, URL oder Nutzdaten als feste Klasse
`bootstrap`, `runtime` oder `http` gemeldet. Die öffentliche Annahme akzeptiert
nur same-origin Browser-POSTs, höchstens 256 Bytes, eine exakte JSON-Struktur
und HTTP-Statuswerte. Sie ist sowohl pro Client als auch global begrenzt;
abgewiesene Payloads werden nicht als Fehlerereignis geschrieben. Damit ist
der Endpunkt kein ungebundener öffentlicher Log-Sink. Backendfehler erzeugen
nur die Kategorie, den sicheren Routenbezug, den Status und den Digest.

## Azure-Aufbewahrung, Menge und Zugriff

Container-Apps-`stdout` fließt in genau den bestehenden Log-Analytics-
Workspace. Standardmäßig gelten 30 Tage Aufbewahrung und 0,5 GB tägliche
Aufnahme; Eingabevalidierungen erlauben höchstens 90 Tage beziehungsweise
1 GB. Application Insights verwendet denselben Workspace, lokale Schlüssel-
Authentifizierung ist aus und seine tägliche Aufnahme ist auf 0,1 GB begrenzt.

Zugriff erhalten nur Maintainer mit Azure-RBAC-Leserechten auf den Workspace
beziehungsweise die Monitoringressourcen. Die bestehende Deployment-Identity
aus #126 bleibt auf die Container App begrenzt und erhält keine Log-, Budget-
oder Monitoringrechte. Exporte, öffentliche Dashboards und eine öffentliche
Statusseite sind nicht vorgesehen.

## Alarme und Kostengrenzen

- Eine Logabfrage alarmiert bei strukturierten `backend_error`- oder
  `frontend_error`-Ereignissen. Sie aggregiert die echte Ereigniszahl und
  verwirft das Aggregat bei `AggregatedValue = 0`; `ResultCount > 0` sieht
  deshalb ohne Fehler keine Ergebniszeile und ab einem Fehler genau eine.
  Der Alarm ist stateful und aktiviert Auto-Mitigation. Während die Bedingung
  besteht, bleibt eine Alarminstanz offen, statt bei jeder Auswertung eine neue
  Meldung zu erzeugen. Bei dieser stündlichen Frequenz beendet Azure die
  Instanz nach drei aufeinanderfolgenden Auswertungen ohne Treffer, also nach
  etwa drei Stunden, und meldet die Entwarnung über das Common Alert Schema
  der Action Group. Der `MetricValue` einer solchen zeitbasierten Entwarnung
  ist [laut Azure Monitor](https://learn.microsoft.com/azure/azure-monitor/alerts/alerts-troubleshoot#the-metricvalue-field-contains-null-for-resolved-log-search-alert-notifications)
  erwartungsgemäß `null`.
- Ein Standard-Webtest prüft nach Aktivierung die #127-Landingpage alle
  15 Minuten aus genau einem expliziten Standort. Die Demo selbst erhält keinen
  periodischen Warm-up-Aufruf und kann deshalb ohne Nutzungsverkehr skalieren.
- Der Uptime-Alarm und beide Budgetmeldungen verwenden dieselbe Azure Monitor
  Action Group. Dadurch lässt sich der Zustellweg unabhängig testen.
- Das monatliche Resource-Group-Budget meldet 80 Prozent tatsächliche Kosten
  und 100 Prozent prognostizierte Kosten. Es stoppt Ressourcen nicht
  automatisch.

### Azure Smart Detection bewusst abgrenzen

Application Insights bringt zusätzlich zu den von lzug definierten Webtests
eigene Smart-Detection-Mechanismen mit. Für neue Komponenten setzt der
AzureRM-Provider deshalb
`features.application_insights.disable_generated_rule = true`; die automatisch
erzeugte externe Failure-Anomalies-Regel wird damit bereits beim Erstellen
deaktiviert. Diese Provider-Option ist nicht rückwirkend.

Für neue und bestehende Komponenten verwaltet OpenTofu außerdem exakt die zehn
provider-nativen `ProactiveDetectionConfigs`. Alle bleiben deaktiviert,
`send_emails_to_subscription_owners` ist `false`, und die Liste zusätzlicher
Empfänger ist leer. AzureRM verwendet für Anlegen und Aktualisieren denselben
idempotenten Update-/Upsert-Pfad auf den festen Child-Ressourcen. Stabile
API-Namen bilden daher sowohl die Adoption des Livebestands als auch eine neue
Umgebung ohne separate Import-IDs ab.

Beim ersten Plan gegen eine bestehende Komponente erscheinen dadurch genau
zehn neue OpenTofu-Ressourcenadressen. Beim Apply aktualisiert AzureRM die
bereits vorhandenen, fest benannten Children und übernimmt sie in den State;
es entsteht keine zweite Regelsammlung. Für eine neue Komponente gilt derselbe
Zehnervertrag. Eine abweichende Anzahl oder ein anderer Name ist **STOP**.

Azure kann unabhängig davon die Plattform-Action-Group
`Application Insights Smart Detection` anlegen. Der verifizierte Livebestand
hat keine direkten E-Mail-Empfänger, aber ARM-Rollenempfänger; er ist daher
nicht empfängerlos. Die Gruppe ist mit keinem expliziten lzug-Webtest-, Fehler-
oder Budgetalarm verbunden, wird nicht importiert oder gelöscht und bildet
nach Deaktivierung sämtlicher Detection-Regeln keinen lzug-Alarmvertrag. Ihre
Existenz bleibt ein dokumentierter Plattform-Side-Effect ohne zusätzliche
OpenTofu-Ressource.

Eine externe
`Microsoft.AlertsManagement/smartDetectorAlertRules`-Failure-Anomalies-Regel
für dieselbe Komponente ist dagegen sicherheitsrelevanter Drift. Vor jedem
späteren Plan mit externem Monitoring muss deshalb der read-only Check
`scripts/check_demo_smart_detection.py` mit der bestätigten Subscription,
Resource Group und dem Application-Insights-Namen erfolgreich sein. Ein
Treffer, eine Subscription-Abweichung oder eine nicht beweisbare Abwesenheit
führt fail-closed zu **STOP**; die Regel wird weder automatisch importiert noch
gelöscht.

Hintergrund sind die Microsoft-Dokumentation zu
[Failure Anomalies](https://learn.microsoft.com/azure/azure-monitor/alerts/proactive-failure-diagnostics),
[Action Groups](https://learn.microsoft.com/azure/azure-monitor/alerts/action-groups)
und der fest gepinnte
[AzureRM-Feature-Vertrag](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/guides/features-block.html.markdown).

`tofu test` plant die Uptime-Ressourcen mit gemockten Providern und prüft das
Landingpage-Ziel, den Alarm, die Action-Group-Bindung, Budgetschwellen,
Logquery, `ResultCount`-Kriterium, die stündliche Auswertung und das
15-Minuten-Uptime-Fenster, Stateful-Auto-Mitigation, Aufbewahrung und Quota.
Es prüft außerdem das Create-Time-
Opt-out, die vollständigen zehn deaktivierten Smart-Detection-Children, die
abgeschalteten Owner-E-Mails, leere Zusatzempfänger sowie das gemeinsame
Adoptions-/New-Environment-Verhalten. Das ist der repositoryseitige Vertrag,
aber kein Nachweis einer real zugestellten Meldung. Der kontrollierte
Live-Nachweis muss separat belegen: keine Auslösung ohne Fehlerzeile, genau
eine offene Instanz ab einer echten Fehlerzeile und deren automatische
Entwarnung nach drei aufeinanderfolgenden fehlerfreien Auswertungen.

## Störungs- und Diagnosepfad

1. Alarmtyp, Zeitpunkt, Deployment-Digest und betroffene sichere Route
   aufnehmen; keine vollständigen Logzeilen in öffentliche Issues kopieren.
2. Liveness (`/api/health`), Readiness (`/api/ready`), Azure-Revision und das
   aktive App-/Seed-Digestpaar read-only vergleichen.
3. In Log Analytics ausschließlich den engen Zeitraum, die Ereignisklasse und
   den Digest abfragen. Fachliche Inhalte, Sessiondaten und Request-Bodies sind
   weder erforderlich noch vorhanden.
4. Bei fehlender Readiness zuerst Init-/Migrations- und Resetnachweis prüfen.
   Bei Livenessfehlern Container-/Revisionzustand prüfen. Bei reinem
   Frontendfehler denselben Digest gegen Browser- und CI-Nachweis abgleichen.
5. Kein einzelnes Image und keine einzelne IaC-Ressource still reparieren.
   Korrektur oder Rollback verwendet den dokumentierten atomaren
   Digestpaarvertrag aus dem Demo-Deployment.
6. Diagnosezugriffe und externe Alarmtests im Umsetzungstask dokumentieren;
   sensible Azure-Ausgaben und lokale Plan-/State-Dateien bleiben außerhalb
   von GitHub.

## Fail-closed Aktivierungsgate

Vor einem echten Plan werden alle folgenden nicht geheimen Eingaben gegen den
aktuellen `master`-Stand und Livezustand neu bestätigt:

| Eingabe | Exakter Vertrag |
| --- | --- |
| `azure_subscription_id` | UUID der isolierten Demo-Subscription |
| `location`, `name_prefix` | freigegebene EU-Region und bestehender stabiler Präfix |
| `demo_artifact_pair` | beide kanonischen `ghcr.io/...@sha256:…`-Referenzen plus Produkt-Tag, vollständiger Commit, in beiden Manifesten digestgebundener Runtimevertrag `lzug-demo-health-ready-v1`, Schemafingerprint und Seed-Revision aus demselben erfolgreichen grünen Publish-/Snapshotnachweis |
| `github_environment_deployment_policy_ids` | bei bestehenden Policies gemeinsam die live gelesenen numerischen IDs für `master` und `snapshot`, nach Aktivierung zusätzlich `release`; leer nur für ein neues Environment ohne diese Regeln |
| `budget_amount_eur` | freigegebener Monatsbetrag, größer 0 und höchstens 100 |
| `budget_contact_emails` | ausdrücklich bestätigte Empfänger der gemeinsamen Action Group |
| `budget_start_date`, `budget_end_date` | gültiger Budgetzeitraum in RFC 3339 UTC |
| `log_retention_days`, `log_daily_quota_gb` | 30 bis 90 Tage und 0,1 bis 1 GB |
| `application_insights_daily_cap_gb` | 0,1 bis 0,5 GB |
| `external_monitoring_enabled` | exakt `true`, erst nach Merge und Veröffentlichung von #127 |
| `landingpage_url` | endgültige öffentliche HTTPS-URL aus #127 ohne Credentials, Query oder Fragment |
| `uptime_frequency_seconds` | exakt 900 Sekunden |
| `uptime_geo_locations` | genau ein ausdrücklich bestätigter Azure-Teststandort |

Vor `tofu plan` wird zusätzlich read-only geprüft:

```sh
python3 scripts/check_demo_smart_detection.py \
  --subscription-id "$AZURE_SUBSCRIPTION_ID" \
  --resource-group "$DEMO_RESOURCE_GROUP" \
  --component-name "$APPLICATION_INSIGHTS_NAME"
```

Fehlt ein Wert, ist #127 nicht gemergt/veröffentlicht, weicht der aktive
Digest ab, erscheint eine externe Failure-Anomalies-Regel für die Komponente
oder enthält der Plan unerwartete Löschungen, Rechte, Secrets, Persistenz oder
weitere Datensenken, lautet das Ergebnis **STOP**. Bei vollständigen Inputs und
grünem Driftcheck werden nur `tofu plan -out=demo-observability.tfplan` und
`tofu show demo-observability.tfplan` ausgeführt und geprüft. Dieser
Repositorytask stoppt ausdrücklich vor `tofu apply`.

### Aktivierungsreihenfolge nach GO P

Der Plan auf `master@33cba0e1afe7eddfbec8cbf646df315464116fec`
mit SHA-256
`3be09805cf09888dc2188444c7765453e597f99a1d528b0b0cb19d4eccde47c4`
enthielt 3 Creates, 6 Updates und 0 Deletes ohne Ersetzungen. Seine übrigen
Action-Group-, Budget-, Fehleralarm-, Logic-App-, CORS-, Digest- und
Aufbewahrungsänderungen entsprachen dem #129-Vertrag. Er bleibt dennoch
dauerhaft **kein Apply-Kandidat**, weil er das `Consumption`-Profil und die
ausgewählten Environment-Policies nicht deklarativ erhielt und das aktive
v0.1.2-Paar `/api/ready` nicht unterstützt.

Die fehlgeschlagenen Tags `demo/v0.2.0-SNAPSHOT.33cba0e` und
`demo/v0.2.0-SNAPSHOT.adbf352` werden weder verschoben, gelöscht, erneut
ausgeführt noch für einen Plan wiederverwendet. Beim zweiten Lauf stoppte die
noch nicht adoptierte Ziel-Policy bereits im Vorjob; Quality, Build, Publish,
SBOM, Provenance und Manifestprüfung wurden dadurch übersprungen. Die
repositoryseitige Korrektur verlegt diese Prüfung hinter die vollständig
belegte Artefaktassembly und vor jede Azure-Anmeldung. Danach ist die
Reihenfolge:

1. vollständige Quality für den neuen aktuellen `master`-Commit,
2. neuer annotierter Snapshot-Tag mit neuer, unveränderlicher App-/Seed-
   Assembly; Quality, Build, Publish, SBOM, Provenance und beide
   Manifestprüfungen müssen grün sein,
3. der vor der IaC-Adoption erwartbare Deploy-STOP ist kein
   Deploymentnachweis und der Tag wird nie erneut ausgeführt oder verschoben;
   das bereits digestgebundene Paar bleibt jedoch der einmalige
   Infrastrukturkandidat,
4. neue lokale Inputs mit allen sieben Paarwerten und beiden live gelesenen
   Policy-IDs,
5. neuer vollständiger OpenTofu-Plan auf exakt dieser SHA; Policy-Ressourcen
   müssen importiert statt dupliziert, das `Consumption`-Profil erhalten und
   die Container-App muss atomar auf das neue Paar wechseln,
6. STOP vor Apply und neues Maintainer-GO, gebunden an SHA und neuen Planhash,
7. nach Apply ein weiterer neuer Snapshot; erst dessen vollständig grüner
   automatischer Publish-/Deploy-/Readiness-/Smoke-Lauf beweist den
   dauerhaften Endzustand.

Weder ein Rückfall auf `/api/health` noch HTTP 401 gelten als Readiness. Das
alte v0.1.2-Paar, der obige Plan und der fehlgeschlagene Snapshot sind keine
zulässigen Inputs für Schritt 5.

Nach einem separaten, plan- und SHA-gebundenen Maintainer-GO folgen Apply,
read-only Ressourcenabgleich, je ein erfolgreicher realer Lauf beider
Webtests, ein Test der gemeinsamen Action Group und die Prüfung, dass beide
Budgetbenachrichtigungen genau diese Gruppe referenzieren. Erst mit belegter
Uptime- und Budgetalarmzustellung kann die Gesamtakzeptanz von #129 erfüllt
und das Issue geschlossen werden.
