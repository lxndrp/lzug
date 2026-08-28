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

## Azure-Aufbewahrung, Metriken und Kosten

Container-Apps-`stdout` fließt in genau den bestehenden Log-Analytics-
Workspace. Standardmäßig gelten 30 Tage Aufbewahrung und 0,5 GB tägliche
Aufnahme; Eingabevalidierungen erlauben höchstens 90 Tage beziehungsweise 1
GB. Zugriff erhalten nur Maintainer mit Azure-RBAC-Leserechten auf den
Workspace und die Container App. Exporte, öffentliche Dashboards und eine
öffentliche Statusseite sind nicht vorgesehen.

Azure Monitor erhebt Container-App-Plattformmetriken im Namespace
`Microsoft.App/containerApps`. Für die Diagnose sind insbesondere
`Replicas` (aktive Repliken, Dimension `revisionName`), `RestartCount`
(kumulierte Neustarts je Replik und Revision) sowie `Requests` (nach Revision
und Statusklasse) relevant. Bei einer Störung werden sie im Azure-Metric-
Explorer zusammen mit Revision, Digest, Liveness, Readiness und den engen Logs
des betroffenen Zeitraums read-only betrachtet.

Es gibt bewusst **keinen** statischen Metrikalarm. Die erwartete Skalierung auf
null macht `Replicas`, CPU-, Speicher- und Request-Werte ohne weiteren Kontext
nicht zu einem belastbaren Fehlersignal. `RestartCount` kann einen Container-
Neustart anzeigen, unterscheidet aber nicht zuverlässig zwischen einem
erwarteten Anlauf nach Skalierung und einem handlungsrelevanten Fehler. Ein
zusätzlicher Alarm würde deshalb nur Rauschen und eine periodische
Kostenposition erzeugen. Dieser Verzicht bedeutet null überwachte
Metrikzeitreihen und keine zusätzliche Metrikalarmgebühr; die Azure-Monitor-
Preise und Freimengen müssen vor jeder späteren Änderung gegen das konkrete
Abonnement geprüft werden.

Application Insights, Standard-Webtests, Uptime-Alarme und Smart Detection
sind kein Teil des OpenTofu-Vertrags. Es gibt keine periodische HTTP-/Uptime-
Prüfung der Landingpage oder Demo. Damit wird die Demo ohne Nutzungsverkehr
nicht künstlich gestartet. Deployment-, Reset- und Landingpage-Smoke-Tests
bleiben die ereignisbezogenen Funktions- und Sicherheitsnachweise.

Die gemeinsame Azure-Monitor-Action-Group bleibt für den Fehleralarm und die
Budgetmeldungen erhalten. Die bestehende Logabfrage alarmiert bei strukturierten
`backend_error`- oder `frontend_error`-Ereignissen. Sie aggregiert die echte
Ereigniszahl und verwirft das Aggregat bei `AggregatedValue = 0`; `ResultCount
> 0` sieht deshalb ohne Fehler keine Ergebniszeile und ab einem Fehler genau
eine. Der Alarm ist stateful und aktiviert Auto-Mitigation. Bei seiner
stündlichen Frequenz beendet Azure die Instanz nach drei aufeinanderfolgenden
fehlerfreien Auswertungen, also nach etwa drei Stunden, und meldet die
Entwarnung über das Common Alert Schema der Action Group. Das monatliche
Resource-Group-Budget meldet 80 Prozent tatsächliche Kosten und 100 Prozent
prognostizierte Kosten; es stoppt Ressourcen nicht automatisch.

Hintergrund sind die Microsoft-Dokumentation zu
[Container-App-Metriken](https://learn.microsoft.com/azure/container-apps/metrics),
[Azure-Monitor-Preisen](https://azure.microsoft.com/pricing/details/monitor/)
und [Action Groups](https://learn.microsoft.com/azure/azure-monitor/alerts/action-groups).

`tofu test` plant den verbleibenden Vertrag mit gemockten Providern und prüft
Budgetschwellen, Logquery, `ResultCount`-Kriterium, stündliche Auswertung,
Stateful-Auto-Mitigation, Aufbewahrung und Quota. Ein expliziter
Negativvertrag verhindert die Rückkehr von Application Insights, Webtests,
Smart Detection und statischen Metrikalarmen. Das ist der repositoryseitige
Vertrag, aber kein Nachweis einer real zugestellten Meldung.

## Störungs- und Diagnosepfad

1. Alarmtyp, Zeitpunkt, Deployment-Digest und betroffene sichere Route
   aufnehmen; keine vollständigen Logzeilen in öffentliche Issues kopieren.
2. Liveness (`/api/health`), Readiness (`/api/ready`), Azure-Revision und das
   aktive App-/Seed-Digestpaar read-only vergleichen.
3. Bei einem Plattformverdacht `Replicas`, `RestartCount` und `Requests` im
   engen Zeitraum und mit ihren Revision-/Replikdimensionen betrachten.
4. In Log Analytics ausschließlich den engen Zeitraum, die Ereignisklasse und
   den Digest abfragen. Fachliche Inhalte, Sessiondaten und Request-Bodies sind
   weder erforderlich noch vorhanden.
5. Bei fehlender Readiness zuerst Init-/Migrations- und Resetnachweis prüfen.
   Bei Livenessfehlern Container-/Revisionzustand prüfen. Bei reinem
   Frontendfehler denselben Digest gegen Browser- und CI-Nachweis abgleichen.
6. Kein einzelnes Image und keine einzelne IaC-Ressource still reparieren.
   Korrektur oder Rollback verwendet den dokumentierten atomaren
   Digestpaarvertrag aus dem Demo-Deployment.
7. Diagnosezugriffe im Umsetzungstask dokumentieren; sensible Azure-Ausgaben
   und lokale Plan-/State-Dateien bleiben außerhalb von GitHub.

## Plan- und Apply-Grenze

Vor einem echten Plan werden alle nicht geheimen Eingaben gegen den aktuellen
`master`-Stand und Livezustand bestätigt: Subscription, EU-Region und stabiler
Präfix, vollständiges `demo_artifact_pair`, vorhandene GitHub-Environment-
Policies, Budgetbetrag und Empfänger, Budgetzeitraum sowie Log-Aufbewahrung und
-Quota. Enthält der gespeicherte Plan andere Änderungen als die erwarteten
Monitoring-Löschungen oder höchstens zwei explizit dokumentierte statische
Container-App-Metrikalarme, muss er vor Apply neu bewertet werden. Container
App, Environment, Revision und Digestpaar dürfen dabei nicht ersetzt oder
verändert werden.

Der Repositorytask stoppt vor `tofu apply`. Ein Apply ist nur nach einem
separaten, an Commit und gespeicherten Plan gebundenen Maintainer-GO zulässig.
