# Kostenbaseline der öffentlichen Demo

## Verbindliches Ziel

Für die öffentliche Demo gilt bei typischer Nutzung ein verbindliches Ziel von höchstens **1,00 EUR pro Kalendermonat**.
Dieser Wert ist zugleich der OpenTofu-Vertrag für das Resource-Group-Budget `budget_amount_eur`; die Eingabevalidierung akzeptiert keinen anderen Betrag.
Das Budget ist eine verzögerte Warnung und keine Kosten- oder Verbrauchsgrenze: Azure sperrt oder beendet Ressourcen dadurch nicht.

Die Beträge unten sind eine versionierte, reproduzierbare Erwartung für die angegebene Nutzung und kein Preisangebot.
Azure-Preise hängen von Region, Vertrag, Währung und Freimengen ab.
Die Baseline wird bei jeder relevanten Preis- oder Infrastrukturänderung neu datiert.

## Typische Nutzung und Annahmen

Die Kalkulation verwendet den Kalendermonat mit höchstens 31 Tagen und den Stand **2026-08-29**:

| Annahme | Wert | Herleitung |
| --- | ---: | --- |
| Geführte öffentliche Sessions | 20 pro Monat | typische Anschauungs- und Smoke-Nutzung, keine Dauerlast |
| App-HTTP-Aufrufe | 25 pro Session plus drei Resetprüfungen pro Tag | höchstens 593 Requests pro Monat; Fehlerwiederholungen zählen nicht zur typischen Nutzung |
| Aktive App-Laufzeit | höchstens 15 Stunden | 20 Sessions × 30 Minuten plus 31 Reset-Warm-ups × 5 Minuten, aufgerundet |
| App-Ressourcen | 0,5 vCPU und 1 GiB RAM | OpenTofu-Template; `min_replicas = 0`, `max_replicas = 1` |
| Resetfrequenz | einmal täglich, 31 Läufe | `Europe/Berlin`, 03:00 Uhr; kein manueller Reset in der Baseline |
| Logic-App-Aktionen | höchstens 15 eingebaute Aktionen pro Resetlauf | maximal 465 eingebaute Ausführungen pro Monat, keine Managed Connectors und keine Retries im Erfolgsfall |
| Ausgehende Daten | höchstens 1 GiB pro Monat | Seiten-, API- und Diagnoseantworten einschließlich Reserve; eingehender Verkehr wird nicht berechnet |
| Kostenpfade | keine Logs, keine Webtests, keine Application Insights, keine Diagnostic Settings, keine zusätzliche Datenbank oder VNET-Ressource | aktueller Infrastrukturvertrag |

Daraus liegen die Container-Apps-Verbrauchswerte deutlich unter den
monatlichen Freimengen: 15 Stunden × 0,5 vCPU ergeben höchstens 27.000
vCPU-Sekunden, 15 Stunden × 1 GiB höchstens 54.000 GiB-Sekunden und die
höchstens 593 HTTP-Aufrufe liegen weit unter 2 Millionen. Die
[Container-Apps-Preisseite](https://azure.microsoft.com/pricing/details/container-apps/)
nennt 180.000 vCPU-Sekunden, 360.000 GiB-Sekunden und 2 Millionen Requests je
Subscription und Monat als freie Menge. Die Init-Container-Ausführung ist in
der Laufzeitreserve enthalten.

Die Logic App nutzt nur eingebaute HTTP-, Steuerungs- und Zeitoperationen.
Die 465 Ausführungen bleiben unter den 4.000 kostenlosen eingebauten Aktionen je Subscription und Monat.
Ein unerwarteter Retry-Sturm oder zusätzliche Workflows gehört nicht zur Baseline und muss im Kostenabgleich als Abweichung erscheinen.

## Ressourcenbezogene Erwartung

| Ressource oder Dienst | Kostenart | Erwarteter Monatsbetrag | Preiseinheit | Annahme und Quelle | Stand |
| --- | --- | ---: | --- | --- | --- |
| Resource Group `lzug-demo-rg` | keine eigene Azure-Nutzungsgebühr | 0,00 EUR | Resource-Group-Monat | eine Resource Group; Kosten entstehen nur durch enthaltene Dienste | 2026-08-29 |
| Container Apps Environment `lzug-demo-env` | nutzungsabhängig, keine Environment-Grundgebühr | 0,00 EUR | vCPU-Sekunden und GiB-Sekunden der Apps | Consumption, Scale-to-zero; [Container Apps-Preise](https://azure.microsoft.com/pricing/details/container-apps/) und [Billing](https://learn.microsoft.com/azure/container-apps/billing) | 2026-08-29 |
| Container App `lzug-demo-app` einschließlich Init-Container | nutzungsabhängig | 0,00 EUR | vCPU-Sekunden, GiB-Sekunden, HTTP-Requests | errechnete Nutzung bleibt unter 180.000 / 360.000 / 2.000.000 freien Einheiten je Subscription; [Container Apps-Preise](https://azure.microsoft.com/pricing/details/container-apps/) | 2026-08-29 |
| Internet-Egress der Container App | nutzungsabhängig | 0,00 EUR | GB aus Azure | höchstens 1 GiB und damit unter den ersten 100 GB/Monat; [Bandwidth-Preise](https://azure.microsoft.com/pricing/details/bandwidth/) | 2026-08-29 |
| Logic App Consumption `lzug-demo-reset` einschließlich Trigger und Actions | nutzungsabhängig | 0,00 EUR | eingebaute Aktionsausführung | höchstens 465 Ausführungen gegenüber 4.000 freien eingebauten Aktionen je Subscription; [freie Azure-Dienste](https://azure.microsoft.com/pricing/free-services/) und [Logic-Apps-Metering](https://learn.microsoft.com/azure/logic-apps/logic-apps-pricing) | 2026-08-29 |
| Logic-App-Run-History und interne Speicheroperationen | nutzungsabhängig, kleiner Restposten | höchstens 0,10 EUR | Speicher-/Aufbewahrungsoperationen | 31 kleine, erfolgreiche Läufe; keine großen Payloads, keine Anhänge, keine Integration-Account-Ressource; [Logic-Apps-Metering](https://learn.microsoft.com/azure/logic-apps/logic-apps-pricing) | 2026-08-29 |
| Azure Monitor Action Group mit einer E-Mail-Adresse | keine Grundgebühr; Benachrichtigungen nur bei Ereignissen | 0,00 EUR | Benachrichtigung | typische Nutzung löst keine Budgetwarnung aus; keine SMS-, Voice-, Webhook- oder Logic-App-Aktion; [Monitor-Kosten](https://learn.microsoft.com/azure/azure-monitor/fundamentals/cost-usage) | 2026-08-29 |
| Resource-Group-Budget `lzug-demo-monthly` | keine eigene Verbrauchsgebühr | 0,00 EUR | Budget-Monat | Budget dient nur Überwachung und Benachrichtigung; [Budget-Tutorial](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets) | 2026-08-29 |
| Managed Identity, RBAC-Rolle und RBAC-Zuweisung | keine eigene Nutzungsgebühr | 0,00 EUR | Control-Plane-Ressource | genau eine systemzugewiesene Identity und eine auf die Container App begrenzte Rolle | 2026-08-29 |
| GitHub Environment und Deployment-Policies | außerhalb der Azure-Abrechnung | 0,00 EUR Azure | GitHub-Konfiguration | nicht Teil der Azure-Resource Group und kein Azure-Dienst | 2026-08-29 |

Die erwartete Summe beträgt damit **höchstens 0,10 EUR pro Monat** und liegt unter dem verbindlichen Ziel von 1,00 EUR.
Der Betrag von 0,10 EUR für die interne Logic-App-History ist eine konservative Planungsreserve; eine reale Überschreitung des Ziels wird nicht durch diese Schätzung legitimiert.

Nicht in der Resource Group enthaltene Kosten, etwa die GitHub-Pages-Site, GHCR-Aufbewahrung, Subscription-Grundlagen oder ein abweichender Azure-Vertrag, werden nicht stillschweigend als kostenlos angenommen.
Sie müssen bei einer Änderung des Veröffentlichungs- oder Subscriptionmodells separat bewertet werden.

## Budgetvertrag

OpenTofu setzt das Resource-Group-Budget auf `1` EUR pro Monat.
Die bestehende Action Group erhält zwei Meldungen:

- **80 Prozent tatsächliche Kosten** als frühe Warnung,
- **100 Prozent prognostizierte Kosten** als Warnung am Zielwert.

Die Empfänger werden ausschließlich lokal beziehungsweise im geschützten Deploymentkontext gehalten; Beispielwerte werden nicht als echte Kontaktadresse veröffentlicht.
Budgetdaten und Warnungen sind wegen der Azure-Auswertung verzögert.
Das Budget sperrt, stoppt oder skaliert keine Ressource und ist deshalb niemals eine Echtzeitgrenze.

## Read-only-Kostenprüfung

Die Prüfung erfolgt manuell für die Demo-Resource-Group und benötigt nur Leserechte auf Cost Management und den Resource Manager.
Sie verändert weder Azure-Ressourcen noch OpenTofu-State.
Nach Ende des Beobachtungszeitraums werden `AZURE_SUBSCRIPTION_ID`, `DEMO_RESOURCE_GROUP`, `COST_FROM` und `COST_TO` lokal gesetzt:

```sh
export AZURE_SUBSCRIPTION_ID="..."
export DEMO_RESOURCE_GROUP="lzug-demo-rg"
export COST_FROM="2026-08-01T00:00:00Z"
export COST_TO="2026-09-01T00:00:00Z"

az rest --method post \
  --url "https://management.azure.com/subscriptions/${AZURE_SUBSCRIPTION_ID}/resourceGroups/${DEMO_RESOURCE_GROUP}/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
  --body "{\"type\":\"ActualCost\",\"timeframe\":\"Custom\",\"timePeriod\":{\"from\":\"${COST_FROM}\",\"to\":\"${COST_TO}\"},\"dataset\":{\"granularity\":\"Monthly\",\"aggregation\":{\"totalCost\":{\"name\":\"PreTaxCost\",\"function\":\"Sum\"}},\"grouping\":[{\"type\":\"Dimension\",\"name\":\"ResourceId\"},{\"type\":\"Dimension\",\"name\":\"Meter\"}]}}" \
  | jq '{columns: .properties.columns, rows: .properties.rows}'
```

Der Abruf ist trotz HTTP `POST` eine reine Cost-Management-Abfrage.
Es werden keine `create`, `update`, `delete`, `start`, `stop`, `tofu apply` oder Infrastruktur-Workflows ausgeführt.
Der Prüfdatensatz wird lokal mit folgenden Feldern abgelegt, ohne Subscription-ID, vollständige Resource IDs, E-Mail-Adressen, Tokens oder andere sensible Abrechnungsdetails in GitHub zu veröffentlichen:

- Zeitraum `COST_FROM` bis `COST_TO` und Abrufzeitpunkt in UTC,
- Resource Group beziehungsweise anonymisierte Ressource/Meter,
- tatsächlicher Betrag und von Azure gelieferte Währung,
- angewendete Umrechnung in EUR, falls die Subscription nicht in EUR abrechnet,
- verwendeter Commit beziehungsweise Baseline-Stand.

Die Resource- und Meterzeilen werden mit der Tabelle oben verglichen.
Eine Ressource, ein Meter oder eine Währung, die dort nicht enthalten ist, wird zuerst aufgeklärt und nicht als Rundungsfehler verworfen.

## Verzögerter Abschluss und Abweichungen

Der abschließende Abgleich erfolgt erst, wenn die entfernten Kostenpfade vollständig aus der Abrechnung abgeklungen sind und der Beobachtungsmonat abgeschlossen ist.
Cost Management kann für Pay-as-you-go-Abonnements bis zu 72 Stunden verzögert sein; nach Monatsende können Abschluss und Nachberechnung bis zum fünften Kalendertag dauern.
Deshalb wird frühestens am sechsten Kalendertag nach `COST_TO` geprüft und bei noch offenen Daten erneut gelesen.
Der Bericht nennt immer den tatsächlich beobachteten Zeitraum und den UTC-Abrufzeitpunkt.

Der normalisierte Monatswert wird gegen 1,00 EUR bewertet.
Liegt er darüber, wird #467 nicht als erfüllt geschlossen: Die Abweichung wird je Ressource und Meter mit Ursache, Zeitraum und weiterem Zielzustand als Issue dokumentiert und erst nach einer separaten Planungsentscheidung neu bewertet.
Ein günstigerer oder älterer Tarif darf die Pflicht zur Aufklärung nicht ersetzen.

## Quellen

- [Azure Container Apps pricing](https://azure.microsoft.com/pricing/details/container-apps/)
- [Azure Container Apps billing](https://learn.microsoft.com/azure/container-apps/billing)
- [Azure Logic Apps pricing and metering](https://learn.microsoft.com/azure/logic-apps/logic-apps-pricing)
- [Free Azure services](https://azure.microsoft.com/pricing/free-services/)
- [Azure Bandwidth pricing](https://azure.microsoft.com/pricing/details/bandwidth/)
- [Azure Monitor cost and usage](https://learn.microsoft.com/azure/azure-monitor/fundamentals/cost-usage)
- [Create and manage budgets](https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets)
- [Understand Cost Management data](https://learn.microsoft.com/azure/cost-management-billing/costs/understand-cost-mgt-data)
