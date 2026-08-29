# Beobachtbarkeit der öffentlichen Demo

Die öffentliche Demo verwendet eine kleine, datenschutzgerechte
Betriebsbaseline. Der Repositoryvertrag ist reproduzierbar; reale Azure-,
Budget-, Alert-, Environment- und Monitoringänderungen benötigen weiterhin ein
separates Maintainer-GO. Eine öffentliche Statusseite gehört ausdrücklich nicht
zu diesem Umfang.

## Getrennte Betriebssignale

- `GET /api/health` ist reine Prozess-Liveness. Die Antwort ist unabhängig von
  Datenbankzugriffen und enthält nur `status = ok`, Produktversion,
  Quellrevision und den Self-Link.
- `GET /api/ready` ist Application-Readiness. Erst eine vollständig
  initialisierte und migrierte Datenbank ergibt HTTP 200 und `status = ready`;
  andernfalls folgen HTTP 503 und `status = unavailable`.
- Azure Container Apps verwendet `/api/health` für Liveness und `/api/ready`
  für Readiness. Deployment-Smoke und Reset prüfen beide Signale getrennt.

Die statische Landingpage aus #127 darf nicht anhand von `/api/health`
weiterleiten. Ihr interaktiver Warm-up nach einem bewussten Klick und der
zugehörige Browservertrag verwenden `/api/ready`.

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
abgewiesene Payloads werden nicht als Fehlerereignis geschrieben. Damit ist der
Endpunkt kein ungebundener öffentlicher Log-Sink. Backendfehler erzeugen nur die
Kategorie, den sicheren Routenbezug, den Status und den Digest.

## Streaming-only, Metriken und Kosten

Das Container-Apps-Environment verwendet den AzureRM-Streaming-only-Vertrag:
`logs_destination = null`. Es besitzt weder eine Log-Analytics-Verknüpfung
noch einen Log-Analytics-Workspace, eine Log-Suchregel oder eine
Diagnostic-Setting-Route. `stdout` und Systemmeldungen werden daher nicht
gespeichert oder periodisch durchsucht. Exporte, öffentliche Dashboards und
eine öffentliche Statusseite sind ebenfalls nicht vorgesehen.

Azure Monitor erhebt Container-App-Plattformmetriken im Namespace
`Microsoft.App/containerApps`. Für die Diagnose sind insbesondere `Requests`
(nach Revision, Replik und Statusklasse), `UsageNanoCores` und
`WorkingSetBytes` (je Revision und Replik) relevant. Bei einer Störung werden
sie im Azure-Metric-Explorer zusammen mit aktiver Revision, Digestpaar,
Liveness und Readiness read-only betrachtet.

Es gibt bewusst **keinen** statischen Metrikalarm. Die erwartete Skalierung auf
null macht CPU-, Speicher- und Request-Werte ohne weiteren Kontext nicht zu
einem belastbaren Fehlersignal. Ein zusätzlicher Alarm würde deshalb nur
Rauschen und eine periodische Kostenposition erzeugen. Die Azure-Monitor-Preise
und Freimengen müssen vor jeder späteren Änderung gegen das konkrete
Abonnement geprüft werden.

Application Insights, Standard-Webtests, Uptime-Alarme und Smart Detection
sind kein Teil des OpenTofu-Vertrags. Es gibt keine periodische HTTP-/Uptime-
Prüfung der Landingpage oder Demo. Damit wird die Demo ohne Nutzungsverkehr
nicht künstlich gestartet. Deployment-, Reset- und Landingpage-Smoke-Tests
bleiben die ereignisbezogenen Funktions- und Sicherheitsnachweise.

Die gemeinsame Azure-Monitor-Action-Group bleibt ausschließlich für die
Budgetmeldungen erhalten. Das monatliche Resource-Group-Budget meldet 80
Prozent tatsächliche Kosten und 100 Prozent prognostizierte Kosten; es stoppt
Ressourcen nicht automatisch.

Hintergrund sind die Microsoft-Dokumentation zu
[Container-App-Metriken](https://learn.microsoft.com/azure/container-apps/metrics),
[Logstreaming](https://learn.microsoft.com/azure/container-apps/log-streaming),
[Logspeicheroptionen](https://learn.microsoft.com/azure/container-apps/log-options),
[Azure-Monitor-Preisen](https://azure.microsoft.com/pricing/details/monitor/)
und [Action Groups](https://learn.microsoft.com/azure/azure-monitor/alerts/action-groups).

`tofu test` plant den verbleibenden Vertrag mit gemockten Providern und prüft
Budgetschwellen, Streaming-only ohne Workspace, Log-Suchalarm oder
Diagnostic-Setting sowie den Ausschluss von Application Insights, Webtests,
Smart Detection und statischen Metrikalarmen. Das ist der repositoryseitige
Vertrag, aber kein Nachweis eines echten Azure-Updates.

## Störungs- und Diagnosepfad

1. Zeitpunkt, sichere Route und den erwarteten Deployment-Digest aufnehmen;
   keine vollständigen Logzeilen in öffentliche Issues kopieren. Mit
   `az containerapp revision list --name "$DEMO_APP" --resource-group
   "$DEMO_RESOURCE_GROUP" --query "[?properties.active].{revision:name,created:properties.createdTime}" -o table`
   die aktive Revision lesen und mit dem vollständigen App-/Seed-Digestpaar
   aus dem erfolgreichen Publish- und Deploymentnachweis vergleichen.
2. Liveness (`/api/health`), Readiness (`/api/ready`), Deployment-Smoke,
   Resetlauf und Anwendungsstatus gemeinsam prüfen. Fehlende Readiness wird
   zuerst gegen Init-/Migrations- und Resetnachweis abgegrenzt; ein einzelnes
   Image oder eine einzelne IaC-Ressource wird niemals still repariert.
3. Nur bei einem konkreten Diagnoseanlass einen begrenzten App-Systemstream
   öffnen und nach spätestens 50 Zeilen oder mit `Ctrl-C` beenden:

   ```sh
   az containerapp logs show \
     --name "$DEMO_APP" \
     --resource-group "$DEMO_RESOURCE_GROUP" \
     --type system \
     --tail 50 \
     --follow
   ```

4. Für die Anwendungsausgabe zuerst Revision und Replik read-only auswählen:

   ```sh
   az containerapp replica list \
     --name "$DEMO_APP" \
     --resource-group "$DEMO_RESOURCE_GROUP" \
     --revision "$DEMO_REVISION" \
     --query "[].{replica:name,containers:properties.containers[].name}" \
     -o table

   az containerapp logs show \
     --name "$DEMO_APP" \
     --resource-group "$DEMO_RESOURCE_GROUP" \
     --revision "$DEMO_REVISION" \
     --replica "$DEMO_REPLICA" \
     --container lzug-demo-app \
     --type console \
     --tail 50 \
     --follow
   ```

   Fehlt wegen Scale-to-zero eine Replik, ist das kein Fehler; dann werden
   Revision, Metriken und die ereignisbezogenen Nachweise verglichen, statt
   durch einen Diagnoseaufruf künstlich Traffic zu erzeugen.
5. Für Probleme des gesamten Environments den ebenso begrenzten
   Environment-Systemstream verwenden:

   ```sh
   az containerapp env logs show \
     --name "$DEMO_ENVIRONMENT" \
     --resource-group "$DEMO_RESOURCE_GROUP" \
     --tail 50 \
     --follow
   ```

6. `Requests`, `UsageNanoCores` und `WorkingSetBytes` nur im betroffenen
   Zeitfenster und nach Revision/Replik dimensioniert im Azure-Metric-Explorer
   lesen. Streamausgaben verbleiben lokal im Diagnosekontext; sensible Azure-
   Ausgaben und Plan-/State-Dateien bleiben außerhalb von GitHub.

## Plan- und Apply-Grenze

Vor einem echten Plan werden alle nicht geheimen Eingaben gegen den aktuellen
`master`-Stand und Livezustand bestätigt: Subscription, EU-Region und stabiler
Präfix, vollständiges `demo_artifact_pair`, vorhandene GitHub-Environment-
Policies, Budgetbetrag und Empfänger sowie Budgetzeitraum. Für diese Änderung
darf der gespeicherte Plan ausschließlich die Log-Analytics-Verknüpfung, den
Log-Analytics-Workspace und die Log-Suchregel entfernen. Jede Ersetzung oder
weitere Mutation ist **STOP**. Container App, Environment, Revision, Ingress,
Identity und Digestpaar dürfen weder ersetzt noch fachlich verändert werden.

Der Repositorytask stoppt vor `tofu apply`. Ein Apply ist nur nach einem
separaten, an Commit und gespeicherten Plan gebundenen Maintainer-GO zulässig.
