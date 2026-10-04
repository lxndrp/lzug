# Komponenten

Die Anwendung bleibt ein modularer Monolith mit Backend, Frontend und
lokaler Betreiber-CLI als Produktkomponenten.
Packaging stellt daraus auslieferbare Varianten zusammen.
Deployment beschreibt ihre Bereitstellung und ihren Betrieb.
Gemeinsame Verträge werden an den Grenzen genutzt, nicht in mehreren
Komponenten nachimplementiert.
Die gemeinsame AIO-, Admintransport- und Lifecyclegrenze legt
[ADR-0033](decisions/0033-aio-betrieb-admintransport-und-lifecycle.md) fest.

## Verantwortungen und Abhängigkeiten

| Bereich | Verantwortung | Zulässige Außengrenze | Maßgebliche Quellen |
| --- | --- | --- | --- |
| Backend | ein autoritativer Prozess für HTTP, Admin-Socket, Lifecycle, Fachservices, Persistenz, Dokumente und Integrationsadapter | OpenAPI/JSON, versionierter Unix-Socket-Vertrag, SQLite und kontrollierte Provideradapter | `backend/src/backend/`, `backend/db/` |
| Frontend | aufgabenorientierte Ausschussoberfläche, Routing, Formulare und sichtbare Zustände | same-origin API über zentrale Modelle und Services | `frontend/src/app/` |
| Betreiber-CLI | portable Orchestrierung von Administration, Diagnose und Lifecycle | bereitgestellter lokaler Socket mit versioniertem Adminvertrag | `operator-cli/cmd/lzug-admin/`, `operator-cli/internal/admincli/`, `operator-cli/internal/tools/cli-reference/`, `operator-cli/.goreleaser.yml` |
| OCI und Self-Hosting | Produktimage `lzug-app`, gehärtete Docker-Referenz und persistentes `/data` | `packaging/product/Dockerfile`, `deployment/self-hosted/compose.yaml` und Containerverträge | `packaging/product/`, `deployment/self-hosted/` und `tests/pester/` |
| Öffentliche Demo | getrenntes Image `lzug-demo`, flüchtige App-/Seed-Assembly, Reset, Promotion und Azure-Deployment | digestgebundene Manifeste, OIDC und Demo-Runtime-Policy | `packaging/demo/contract.py`, `packaging/demo/runtime/`, `packaging/demo/artifacts.py`, `packaging/demo/`, `deployment/demo/infra/`, `packaging/demo/tests/`, Demo-Workflows |

`packaging/product/` und `packaging/demo/` erzeugen die Produkt- und Demo-Artefakte.
Komponenteneigene Paketierung bleibt bei ihrer Komponente, etwa GoReleaser
unter `operator-cli/`.
`deployment/self-hosted/` beschreibt den selbst betriebenen Produktcontainer;
`deployment/demo/` besitzt Azure-Infrastruktur, Deployment und Reset der öffentlichen Demo.
Der Repository-Root bleibt der gemeinsame Docker-Buildkontext.

Das Frontend greift nicht direkt auf Persistenz zu.
Die Go-CLI kennt weder Datenbankpfad noch SQL und enthält keine Fach-,
Migrations-, Backup- oder Restorelogik.
Die age-Hülle bleibt ihre einzige kryptographische Verantwortung; private
Schlüssel verlassen den Bedienrechner nicht.
Demo-Policy und Deploymentautomation dürfen Produktregeln nur einschränken oder
synthetische Erweiterungen aktivieren, aber keinen zweiten Produktkern bilden.

## Eigentümermatrix der Konfiguration

Die Matrix ordnet gemeinsame Konfiguration und variantenspezifische Dateien ihren Eigentümern zu.
Ein Pfad bleibt nur dann am Root, wenn er mehrere Komponenten versorgt,
als kanonischer Standard-Einstieg erwartet wird oder den unveränderten
Buildkontext voraussetzt.

| Datei | Eigentümer | Entscheidung und Begründung |
| --- | --- | --- |
| `.mise.toml` | Repository | Am Root behalten: ein gemeinsamer Toolchain-Pin für Python, Node.js, Go, Hugo, Lychee, uv, Task, Syft, GoReleaser und OpenTofu. |
| `Taskfile.yml` | Repository | Am Root behalten: öffentliche Namen, komponentenübergreifende Abhängigkeiten und Quality-Aggregation; Implementierungsabläufe liegen in den Taskfiles ihrer Eigentümer. |
| `pyproject.toml` | Python-/Dokumentations-Toolchain | Am Root behalten: Backend, Demo, Skripte, Tests und MkDocs teilen ein uv-Projekt und einen Tooling-Vertrag. |
| `uv.lock` | Python-/Dokumentations-Toolchain | Am Root behalten: einziger Lockfile für das gemeinsame uv-Projekt; kein zweites Python-Toolingprojekt. |
| `.python-version` | Python-/Dokumentations-Toolchain | Am Root behalten: alle Python-Verbraucher verwenden dieselbe Version. |
| `.node-version` | Frontend | Nach `frontend/.node-version` verschoben: die Versionsdatei gehört ausschließlich zum npm-/Angular-Verbraucher. |
| `mkdocs.yml` | Dokumentation | Nach `docs/mkdocs.yml` verschoben: MkDocs-Konfiguration und Dokumentationsquellen liegen zusammen. |
| `deployment/self-hosted/.env.example` | OCI-/Self-Hosting | Beispielvariablen direkt neben dem Compose-Einstieg. |
| `packaging/Taskfile.yml` | Packaging | Bindet Product- und Demo-Aufgaben unter ihrem jeweiligen Eigentümer ein. |
| `packaging/product/Taskfile.yml` | OCI-/Self-Hosting | Produktimage-Build und SBOM. |
| `packaging/product/Dockerfile` | OCI-/Self-Hosting | Produktimage-Build; Docker baut weiterhin mit dem Repository als Kontext. |
| `packaging/demo/Dockerfile` | Öffentliche Demo | Erstellt die Demo-App-Assembly aus dem Root-Buildkontext. |
| `packaging/demo/Dockerfile.seed` | Öffentliche Demo | Erstellt die Seed-Assembly aus dem Root-Buildkontext. |
| `deployment/self-hosted/compose.yaml` | OCI-/Self-Hosting | Produktbetriebskonfiguration; relative Host-Pfade bleiben auf den Repository-Root bezogen. |
| `.dockerignore` | OCI-/Self-Hosting | Am Root behalten: technisch an den unveränderten Root-Buildkontext gebunden. |
| `.github/` | Repository | Am Root behalten: GitHub erwartet Workflows, Vorlagen und Dependabot-Konfiguration dort. |
| Community-, Lizenz- und Support-Dateien | Repository | Am Root behalten: GitHub- und Community-Standards sowie rechtliche Hinweise erwarten diese Einstiege dort. |

Der Root-Taskgraph erhält die stabilen öffentlichen Einstiege und ordnet
komponentenübergreifende Erzeuger und Verbraucher.
`operator-cli/Taskfile.yml` besitzt GoReleaser-Paketierung und
Reproduzierbarkeit, `docs/Taskfile.yml` den Publikationsaufbau und seine
Artefaktprüfungen, `packaging/Taskfile.yml` verbindet die Eigentümeraufgaben,
`packaging/product/Taskfile.yml` Produktimage und SBOM,
`packaging/demo/Taskfile.yml` Demo-Tests, Seed-/App-Assembly und Smoke-Verbrauch sowie
`frontend/Taskfile.yml` Transportgenerierung, Produktionsbuild und dessen
Verbraucher.
Lokale npm-Einstiege bleiben selbständig nutzbar.
Der Frontend-Adapter ruft keine Task-Aufträge mehr auf; die Task-Abhängigkeiten
machen die Transportgenerierung und Buildreihenfolge sichtbar.

Der lokale Frontend-Quality-Auftrag baut das Produktionsbundle einmal pro
Tasklauf.
Der Produktions-E2E-Test verbraucht diesen Build; der separate
Entwicklungsserver-E2E-Test bleibt erhalten.
Unabhängige Komponenten bleiben parallel ausführbar.

## Backend

Der verbindliche Zielvertrag für Modulverantwortungen, Portinventar,
Transaktionsmatrix, Lebensdauern und Migration steht im
[Backend-Vertrag](backend-architecture-contract.md).
Die folgende Beschreibung dokumentiert die konkrete Implementierung dieser
Revision und ersetzt den Zielvertrag nicht.

`backend.fastapi_assembly.create_app` ist die produktive HTTP-Assembly innerhalb
des einen autoritativen Backendprozesses.
Sie ordnet Konfiguration, Transportgrenze, Fehlerabbildung, fachliche
Routerregistrierung und OpenAPI-Assembly zu.
`backend.fastapi_master_data` besitzt die Router für Stammdaten,
Organisation und Prüfungsorte; `backend.fastapi_app` enthält die verbleibenden
HTTP-Handler und die gemeinsamen Registrierungsgrenzen.
`backend.fastapi_operations_routes` besitzt die Router für Runtime,
Authentisierung, Session und Observability.
`backend.fastapi_integration_routes` besitzt die Router für Kalender,
Benachrichtigungen sowie Abwesenheit und Vertretung.
`backend.fastapi_http` stellt explizite Response-, Attachment- und
Same-Origin-Helfer bereit.
FastAPI übernimmt die Responsemodell-Verarbeitung und OpenAPI-Abbildung der
eingebundenen Router direkt; eine manuelle Responsefeld-Rekonstruktion gibt es
nicht.
`backend.fastapi_planning_router` besitzt die Planungsübersichten,
Vorschlags- und Bestätigungsaggregate, Planfolgen, Verfügbarkeitsübergänge und
die zugehörigen Planungsressourcen.
Request-Payloads sind über `backend.api_contracts` als native FastAPI-Parameter
mit Pydantic-Modellen deklariert.
FastAPI verwendet damit dasselbe Modell für Laufzeitvalidierung und
OpenAPI-Komponenten; eine manuell expandierte zweite Schemafassung existiert
nicht.
Fachlich variable generische Ressourcen teilen sich den offenen
`DomainResourceWrite`-Vertrag, während eigenständige Befehle engere Modelle
verwenden.
`backend.server` startet den Prozess über Uvicorn;
`backend.application.transport` bildet den gemeinsamen Anwendungsvertrag für
HTTP- und Adminadapter ab.
`backend.application.planning_payloads` konvertiert Planungsbefehle ohne
Persistenzzugriff; `resource_authorization` prüft Ressourcenaktionen und bindet
serverseitige Akteurfelder.
`application.resource_access` besitzt die Query-Verträge und materialisierten
Werte für Ausschuss-/Rundenbesitz, Membership-Fakten und sichtbare Projektionen.
Die SQLite-Implementierung in `persistence.resource_access` hält Modellzugriff
und SQL-Prädikate hinter diesen Verträgen.
Bei Updates wird zuerst der gespeicherte Quellbesitz autorisiert;
Payloadwerte dürfen die Quelle nicht ersetzen.
Bereits bestehende Quell-/Zielwechsel prüfen zusätzlich den Zielscope,
während andere Ownershipfelder über den generischen HTTP-Vertrag unveränderlich bleiben.
Sichtbare Listen und Einzelabfragen werden bereits in SQL begrenzt;
historische Rundenzuordnungen und aktive Kandidatenzuständigkeit behalten ihre
unterschiedlichen Sichtbarkeitsregeln.
Zusammengehörige Autorisierungs- und Sichtbarkeitsabfragen verwenden den
Query-Port innerhalb eines expliziten SQLite-Lese-Snapshots.
Technische Abfragefehler bleiben von fachlichen `ForbiddenRequestError`-
Entscheidungen unterscheidbar.
Die generischen Schreibübergänge prüfen veränderliche Ownership-Voraussetzungen
zusätzlich mit demselben Query-Vertrag innerhalb ihrer Schreibtransaktion.
Bei scoped HTTP-Schreibvorgängen beginnt SQLite den Schreib-UoW mit
`BEGIN IMMEDIATE`, damit keine konkurrierende Ownership-Änderung zwischen
Revalidierung und Mutation committet.
Die vorherige HTTP-Prüfung ersetzt diese UoW-Prüfung nicht.
Die Ausführung eines Fachbefehls bleibt eine eigene Servicetransaktion.
Session, CSRF, Actor, Ausschuss-Scope und Fehlerübersetzung liegen am
HTTP-Rand, während der synchrone Anwendungskern frameworkunabhängig bleibt.

`identity.people` besitzt Ports für Personen- und Membership-Schreibvorgänge
sowie Login- und Actor-Projektionen.
`persistence.identity` implementiert sie für SQLite und projiziert
Mitgliedschaften für Listen über die bestehende Query-Grenze aus #1072.
`composition` wählt beide Identity-Adapter.
Personen- und Membership-Änderungen öffnen ihren Schreib-UoW über Identity;
die Membership-Autorisierung verwendet darin die Ownership-Abfragen aus #1072
und prüft die gespeicherte Actor-Mitgliedschaft, ihre Managementrolle und die
authentisierte Person erneut.
Der HTTP-Rand übergibt Actor-Membership-IDs und die authentisierte Person-ID
als Werte.
`identity.committee_admin` verwendet ebenfalls einen Identity-eigenen UoW-Port
für Ausschuss-Masterdaten und ihre PATCH-/DELETE-Routen sowie für Bootstrap,
Abschluss, Wiedereinladung und Ausschuss-Lifecycle.
Seine Committee-, Person-, Membership-, Account-, Invitation- und
Operationsergebnisse sind strukturelle Werte; SQLAlchemy-Objekte verlassen
Persistence nicht.
`AuthorizationService` baut seinen serverseitigen Scope aus der Identity-
Membership-Projektion auf.
Die SQLite-Projektionen sind unveränderliche, strukturell kompatible Werte;
Persistence importiert die Identity-Porttypen dafür nur unter
`TYPE_CHECKING`.
Planning behält Kandidaten- und Rundenregeln.

Die Kandidatentage sind der erste Planning-Port-Pilot:
`backend.planning.candidate_days` enthält den typisierten Generierungsbefehl,
das Ergebnis, die Providerabstraktion und den Unit-of-Work-Vertrag ohne
Persistenz-, FastAPI- oder Feiertagsbibliotheksimport.
`backend.persistence.candidate_days` setzt den Planning-UoW mit einer
SQLite-Session um; `backend.integrations.holiday_provider` implementiert den
Planning-owned Feiertagsvertrag.
`backend.composition.candidate_day_service` wählt beide konkreten Adapter.
Der `RequestContext` übergibt der Factory den pro Sitzung durch die
Runtime-Policy ausgewählten Datenbankpfad. Dadurch bleiben Produkt- und
Demo-Datenbanken getrennt und jede Generierung erhält ihren eigenen UoW.
Das Lebensdauerdiagramm und ein konkreter Ablauf stehen im
[Backend-Vertrag](backend-architecture-contract.md#vertikaler-pilot-kandidatentage).
Andere Planning-Services verwenden weiterhin ihre dokumentierten Übergangspfade.

In `execution.absence` und `execution.exam_protocols` bleiben die öffentlichen
Servicebefehle die autoritative Grenze für Zustandsübergänge.
Der Runden-Lifecycle ist im Ist-Zustand noch nicht in diese Modulgrenzen
aufgeteilt: FastAPI ruft `context.exam_round_lifecycle_service` auf, und der
Service öffnet eigene Sessions und greift direkt auf Planning-, Execution-
und Assessment-Daten zu.
Der gemeinsame Application-UoW mit Planning-, Execution- und Assessment-Ports
ist der Zielvertrag aus
[Backend-Vertrag](backend-architecture-contract.md#port-inventar), keine
bereits umgesetzte Laufzeitarchitektur.
Die Ergebnisänderung auf einem geschlossenen Prüfungstag verwendet heute
`ExamResultService` mit Execution-Prüfung und -Abschluss im selben
Session-Kontext; die Ziel-Orchestrierung über Application-Ports steht separat
im Backend-Vertrag.
Benannte Vorbedingungsprüfungen lesen den aktuellen Stand in derselben Session;
Versions- und Replay-Prüfungen behalten ihre Reihenfolge vor der Mutation.
Audit und die jeweils zugehörigen Änderungen werden innerhalb der
Servicetransaktion atomar gespeichert.
Kalenderfolgen folgen nach dem Planning- oder Execution-Fach-Commit und bleiben
bei Fehlern getrennt wiederholbar offen.
Benachrichtigungen folgen jeweils dem Commit des auslösenden Fachbefehls:
Planereignisse dem Planning-Commit, Execution-Ereignisse dem Execution-Commit.
Eine Wiederholung erzeugt keine zusätzlichen Rundenentscheidungen oder
Wiederöffnungsaufgaben.
`identity.committee_admin` prüft die Wiedereinladungsberechtigung vor dem
Austausch abgelaufener Tokens in der bestehenden Schreibtransaktion.
`identity.local_auth` trennt Konto- und Kennwortprüfung von der atomaren
Verwendung des zweiten Faktors.
TOTP-Replay-Schutz, Recovery-Code-Verbrauch, Kennwort-Rehash und Sessionwechsel
bleiben Teil einer gemeinsamen Transaktion mit generischen Anmeldefehlern und
Dummy-Hash-Prüfung für unbekannte Konten oder Konten ohne Kennwort.
Identity besitzt dafür typisierte Konto-, Token-, Faktor-, Session- und
Schlüsselzugriffsverträge.
`persistence.auth` und `persistence.local_auth` halten SQLAlchemy, SQLite und
Dateizugriff am Adapterrand; der Composition Root wählt die konkreten Adapter.
Backup und Restore beziehen denselben Instanzschlüssel über den Schlüsseladapter.

`integrations.calendar` ist der heutige Legacy-Pfad für lokale Kalenderlogik:
`CalendarService` materialisiert bestätigte Zuweisungen als `CalendarEvent`-
Projektion in SQLite und rendert daraus ICS.
Er ruft keinen externen Kalenderprovider auf.
Der aktuelle Code codiert Eventgenerationen in `source_key` und
`external_event_id`; Inhaltsänderungen erhöhen die Eventversion und eine
Reaktivierung erzeugt eine weitere Generation.
`planning.plan_consequences` besitzt und leitet Kalenderaufträge nach dem
Plan-Commit in einem separaten, idempotent wiederholbaren Planning-UoW ab.
Scheitert die Ableitung, bleibt der bestätigte Plan bestehen; der Request
meldet `derivation_status=missing`, und `process_due` kann die Ableitung
erneut ausführen.
Dieser Pfad betrifft die aus bestätigten Planrevisionen abgeleiteten
Kalenderfolgen.
Er ist nicht mit den direkten Kalenderaufrufen aus dem Abwesenheitsprozess
oder der Rundungsabsage gleichzusetzen.
`_process_calendars` gruppiert sie pro Runde, aktualisiert die Projektion in
einem separaten Datenbank-UoW und speichert danach Auftragsstatus, Event-ID
und Eventversion in einem weiteren UoW.
Heute ruft Planning dafür den konkreten `CalendarService` auf; künftig
orchestriert Application die Projektion über einen typisierten Calendar-Port
und verwaltet Taskstatus, Claim und Retry in seinem consumer-eigenen Vertrag.
`sync_round` verarbeitet die Eventänderungen einer Runde in einem UoW;
ein Fehler bei einem späteren Payload rollt frühere Änderungen dieses Laufs
zurück.
Heute liest `_complete_calendar_task` anschließend `CalendarEvent` direkt in
Planning, um Event-ID und Version zu übernehmen; dieser ORM-Zugriff und die
Planning-eigene Taskpersistenz werden nach dem Handoff entfernt.
`list_events`, `feed_ics` und `event_ics` synchronisieren über `sync_person`
ebenfalls vor dem Lesen oder Rendern; Refresh und Read laufen in getrennten
Session-Scopes.
Nur `feed_ics` validiert dabei ein Feed-Credential.
Heute beschränkt die Feedprüfung die Person nur darauf, mindestens eine aktive
Mitgliedschaft zu haben; die Synchronisierung und Ausgabe filtern anschließend
nach `person_id`.
Bei aktivem Committee A und deaktiviertem Committee B können so weiterhin
Kalenderereignisse aus B synchronisiert oder ausgegeben werden.
Die Umsetzung von #1078 muss stabile Identitäten und Generationen über
Wiederholungen und Planänderungen sowie diese Sync-Seiteneffekte erhalten.
Sie bezieht Planungsdaten über einen typisierten Snapshot aus einem
calendar-eigenen Port, den ein Planning-Adapter erfüllt.
Das Ziel aus #1081 lässt Planning die Folgen beschreiben und verlagert deren
Ausführung in `application`.
Application konsumiert dafür einen eigenen Calendar-Service-Port, erhält
Event-ID und Eventversion als typisiertes Ergebnis und speichert den
Folgeauftragsabschluss.
Der Composition Root verdrahtet Calendar-Snapshot-Port, Planning-Adapter und
Application-Port.
Der direkte Planning-Aufruf von `CalendarService` und der ORM-Zugriff in
`_complete_calendar_task` sind Übergangspfade und entfallen mit dieser
Orchestrierung.
Eine zusätzliche Generation-Fencing-Garantie für verspätete Task-Abschlüsse
ist damit nicht festgelegt.

Weitere heutige Kalenderpfade liegen in `execution.absence`:
`select_replacement` ermittelt über `_report_round_id` eine Runde nur für
einen offenen Prüfungstag und ruft dann `sync_round` vor der
Abwesenheitsmutation auf.
Nach dem Commit ruft es `sync_round` erneut auf, ebenfalls nur bei offenem
Prüfungstag.
Der Zielvertrag entfernt diesen Pre-Sync.
Nur wenn der Prüfungstag beim `select_replacement`-Commit offen ist, speichert
die Execution-Folgequelle im selben Mutation-UoW das unveränderliche
Before-Image einschließlich des Guard-Snapshots `closure_status == "open"`,
Assignment-ID, alter Empfänger-Membership-ID und materialisiertem Eventinhalt.
Generationen gehören ausschließlich Calendar und werden nicht von Execution
vorhergesagt oder gespeichert.
Application replayt diese bereits autorisierte Quelle samt Guard-Snapshot
ohne den zwischenzeitlich veränderlichen Tagesstatus neu zu bewerten und
übergibt das Image an den Calendar-Port: dieser storniert die alte Generation
und erzeugt die stornierte Zeile aus dem Before-Image auch dann, wenn noch
keine Projektion existiert; danach synchronisiert er die neue
Zuweisungsgeneration.
Wenn der Tag beim Mutation-Commit den Status `reopening` hat, entstehen aus
`select_replacement` weder Before-Image noch Calendar-Quelle.
So bleiben Abwesenheitsmutation und Wiederherstellung der alten
Kalenderprojektion/Eventzeile nach Prozessabbruch wiederholbar.
Die unveränderliche `replacement_selected`-Notification-Quelle friert im
gleichen Cross-Domain-UoW den bisherigen Assignee, das Ersatzmitglied und alle
übrigen aktiven Ausschussmitglieder als ursprüngliche Empfänger-IDs ein.
Calendar serialisiert die Generationreservierung je Assignment in seinem
eigenen Repository-UoW und speichert die idempotente Zuordnung von stabilem
Quellursprung zu Generation.
`sync_round`, `sync_assignment` und `sync_person` kombinieren vor jeder
Assignment-Reconciliation den Planning-Snapshot mit der neuesten Execution-
Folgeversion samt Cancellation-Tombstone. Ein verzögerter Planning-Auftrag
reaktiviert keine stornierte Zuweisung; nur eine höhere Execution-Folgeversion
kann sie wieder aktivieren. ICS-read-triggered Sync und Before-Image-Replay
reservieren ausschließlich über denselben Calendar-Allocator.
Damit kann ein Read-Sync die Ersatzprojektion bereits anlegen, ohne dass ein
späteres Replay der alten Empfängerzeile eine UID-Kollision oder zweite
aktive Generation erzeugt; Wiederholungen behalten dieselben
Origin-zu-Generation-Zuordnungen.
Wiederöffnung stellt im Execution-Zustand den ursprünglichen
Assignee wieder her und ruft `sync_round` nach dem Commit nur für einen
offenen Prüfungstag auf.
Dieser Sync storniert das Ersatz-Event mit Versionssprung und erzeugt für den
ursprünglichen Assignee eine neue Eventgeneration.
Abbruch ruft `cancel_assignment` nach dem Commit ebenfalls nur für einen
offenen Prüfungstag auf.
Diese Aufrufe sind direkte synchrone Folgen ohne dauerhaften Application-
Auftrag und ohne garantierte Wiederholung nach Prozessabbruch.
Eine Rundungsabsage verhält sich anders:
`ExamRoundLifecycleService` setzt nicht stornierte `CalendarEvent`-Zeilen mit
`date >= now[:10]` während derselben Rundungsentscheidungs-Transaktion auf
`cancelled` und erhöht ihre Version.
Der inklusive Tages-Cutoff umfasst damit alle Events des Entscheidungstags
und späterer Tage, auch wenn ein Eventzeitpunkt am Entscheidungstag bereits
vergangen ist.
Damit committen Rundungsentscheidung und lokale Kalenderstornierung gemeinsam;
es gibt für diesen Pfad keinen nachgelagerten Calendar-Sync-Auftrag.

Im Ziel materialisiert Application im gemeinsamen UoW vor der
Rundungsentscheidung die vollständige Empfängermenge: alle Planning-
Zuweisungen, aktive Vorsitz-/Stellvertretungs-Memberships aus Identity und
alle nicht stornierten künftigen Calendar-Projektionen mit
`date >= decision_date`. Der Calendar-Anteil umfasst noch aktive Events
veralteter oder ersetzter Assignees; die übrigen Quellen behalten bisherige
Empfänger auch ohne Eventprojektion bei. Planning speichert die vereinigten
Membership-IDs, das Entscheidungsdatum und die Notice-Beschreibung atomar mit
der Rundungsentscheidung und ihrer unveränderlichen Folgequelle. Nach dem
Commit storniert Calendar die Events mit demselben inklusiven Datum. Replay
verwendet die gespeicherten Empfänger-IDs und rekonstruiert sie nicht aus
inzwischen veränderten Projektionen oder Memberships.

Die Composition Root teilt einen prozessweiten Feed-Lifecycle-Lock mit
Token-ICS-Reads, Rotation und explizitem `DELETE /api/calendar/feed`.
Der Lock schützt nur kurze Credential-Prüfungen, Revalidierungen und Commits;
Sync und ICS-Rendering laufen außerhalb.
Ein Read prüft vor der Arbeit Credential-Generation und Identity-Scope,
materialisiert den Read-Snapshot unter kurzer Sperre und revalidiert unmittelbar
vor Rückgabe Credential-Generation und Identity-Scope erneut.
Hat `DELETE` vorher widerrufen, wird das gerenderte Ergebnis verworfen.
Hat sich der Scope seit dem Snapshot geändert, verwirft Calendar das gesamte
gerenderte ICS-Ergebnis.
GET-Refreshes, initiale Aktivierung, Rotation und Pending-Retries nutzen je Feed
denselben Sync-Coordinator: pro Feed läuft höchstens ein Sync-UoW, und Aufträge
derselben Credential- oder Pending-Generation teilen ihn. `DELETE` setzt zuerst
unter einem kurzen Commit-Gate den prozesslokalen Revocation-Fence; wartende
Reads und Sync-Aufträge starten keinen weiteren UoW, ein aktiver Sync rollt
seinen begrenzten UoW zurück. Nach dessen Ende committet `DELETE` die dauerhafte
Revocation-Generation. Der Commit-Gate schützt nur letzte Cancellation-Prüfung
und Sync-Commit, nicht den gesamten Sync.
Initiale Aktivierung verwendet ebenfalls eine nicht-geheime Pending-Generation,
die `DELETE` fencen kann, bevor ein Credential angelegt wird.
Nach dem Ende des aktiven UoW committet `DELETE` Widerruf sowie Löschen oder
Fencing eines Pending-Standes atomar; ein späterer Rotationsfinalizer kann den
widerrufenen Feed dadurch nicht reaktivieren.

Bei fehlgeschlagenem Aktivierungs-/Rotations-POST gehören Status-Reload und
Einmal-URL-Löschung zur UI-Feature-Adapter-/State-Orchestrierung;
die reine `presentation` rendert nur den resultierenden Zustand.
Die URL wird vor dem Reload verborgen und nie aus dem status-only GET
rekonstruiert, auch wenn dieser `active=true` meldet.
Scheitert der Reload, darf ein zuvor aktiver Status nicht als aktuell gelten.
Diese Stelle dokumentiert den Vertrag; #1070 ändert keinen
Frontend-Produktcode.
Die Calendar-Garantie, dass das alte Token nach dem Widerrufscommit ungültig
ist, gilt unabhängig vom Frontend-Fehlerpfad.

Heute speichert `activate` beziehungsweise `rotate` das Credential vor dem
anschließenden Sync.
Bei Rotation wird das alte Credential dadurch vor dem fehleranfälligen Sync
ungültig; schlägt der Sync fehl, bleibt jedoch das neue Token-Hash aktiv,
obwohl dessen einmalige URL nicht zurückgegeben werden konnte.
Zielvertrag für die initiale Aktivierung bleibt Sync-first:
erst lokale Projektion im eigenen Calendar-UoW erfolgreich aktualisieren,
dann das Credential atomar anlegen und dessen URL einmalig zurückgeben.
Bei Rotation wird das alte Credential zuerst in einem eigenen atomaren
Calendar-UoW widerrufen und ein nicht-geheimer Pending-Generationsstand
gespeichert.
Scheitert dieser erste Commit, bleibt die bisherige Generation aktiv und
Calendar beginnt keinen Sync.
Der alte Token ist ab diesem Commit ungültig, auch wenn der folgende Sync
scheitert; der Pending-Stand bleibt für einen ausdrücklichen Retry erhalten.
Ein Retry synchronisiert erneut und darf die neue Token-Generation nur per
CAS auf genau diesen Pending-Stand aktivieren.
Der bestehende Aktivierungs-POST prüft diesen persistierten Pending-Stand
unabhängig vom `rotate`-Argument zuerst und setzt ihn fort, ohne ein weiteres
Pending anzulegen oder erneut zu widerrufen.
Damit setzt auch `rotate=false` nach Reload den Retry fort; ebenso setzt
`rotate=true` aus einem noch aktiven, inzwischen veralteten UI-Zustand denselben
Pending-Stand fort.
Der Statusvertrag zeigt kein Pending-Feld: nach dem Widerrufscommit meldet er
`active=false`, sodass die bestehende UI nach Reload den Button
„Persönlichen Feed aktivieren“ zeigt.
Ein Syncfehler liefert den stabilen Retry-Fehler im bestehenden HTTP-Format
ohne Secret; der folgende POST setzt den gespeicherten Pending-Stand fort.
Nach jedem fehlgeschlagenen Aktivierungs-/Rotations-POST lädt die UI den
Feedstatus neu und aktualisiert ihr `calendar`-Signal mit der Serverantwort.
Zugleich löscht oder verbirgt sie sofort die lokal gehaltene einmalige
`feedUrl`; ein Status-Read enthält kein Secret und darf den Link nie
wiederherstellen.
Nach einem Widerrufscommit zeigt dieser Read `active=false` und die vorhandene
Aktivierungsaktion führt den Pending-Retry aus.
Meldet der Status-Read `active=true`, bleibt der Link dennoch verborgen; bei
unbekanntem Secret kann die Person bewusst erneut rotieren.
Scheitert auch der Status-Read, bleibt die alte URL verborgen und der zuvor
geladene Status wird als veraltet oder unbekannt behandelt, nicht als aktuell
aktiv bestätigt.
Ein pro-Feed Lifecycle-Lock aus der Composition Root schützt kurze
Credential-Prüfungen und -Commits; Sync, Snapshot und Rendering laufen
außerhalb. Sein Registry-/Serviceobjekt wird prozessweit geteilt und nicht pro
`RequestContext` oder `CalendarService` instanziiert.
ICS prüft Credential-Generation und Identity-Scope vor der Arbeit, prüft den
Read-Snapshot unter kurzer Sperre und unmittelbar vor Rückgabe Credential-
Generation und Identity-Scope erneut. Bei einer Scope-Änderung seit dem
Snapshot verwirft Calendar das gesamte materialisierte ICS-Ergebnis; es muss
keine gerenderte Antwort nachträglich parsen oder filtern. Alle Sync-Auslöser
gehen durch den je Feed serialisierten Coordinator; Rotation committet Widerruf und
Pending-Generation unter dem Lifecycle-Lock, synchronisiert außerhalb und
finalisiert nach erneuter Pending-Prüfung unter dem Lock. `DELETE` setzt unter
dem Commit-Gate zuerst ein prozesslokales Abbruchsignal, wartet ohne beide Locks
auf Rollback oder Abschluss des aktiven UoW und committet danach die dauerhafte
Revocation-Generation. Wartende Aufträge starten nach dem Fence nicht; ein
wartender Finalizer mit veraltetem Pending-Stand kann den Feed nicht reaktivieren.
Konkurrierende und veraltete Requests erhalten stabile
`FeedAlreadyActive`-, `FeedRotationPending`- oder `FeedConflict`-Fehler ohne
Secret und können weder die Gewinner-URL ungültig machen noch rohe
Unique-Constraint-Fehler auslösen.
Token-ICS-Reads und Rotation nutzen dieselbe Sperre nur für Credential-Prüfungen
und -Commits. Der Read prüft Token und Identity-Scope vor Sync, revalidiert den
Snapshot unter kurzer Sperre und liest Credential-Generation sowie Identity-
Scope unmittelbar vor Rückgabe erneut. Bei einer Scope-Änderung seit dem
Snapshot verwirft Calendar das gesamte materialisierte ICS-Ergebnis; Sync und
Rendering liegen außerhalb.
Rotation hält die Sperre für Widerrufscommit sowie spätere Pending-Revalidierung
und Finalisierung; ihr Sync läuft außerhalb.
Die Garantie gilt prozessweit im einzelnen autoritativen Backendprozess;
mehrere Serverprozesse für dieselbe Datenbank sind nicht unterstützt.
Erst der erfolgreiche Finalisierungscommit gibt die neue URL einmalig aus.
Bei Commitfehler wird kein Secret ausgegeben; bleibt der Pending-Stand
erhalten, kann der Sync mit einer neuen Secret-Erzeugung wiederholt werden.
Ist die Finalisierung bereits committet und nur die Antwort verloren,
bleibt das Secret unverfügbar und eine neue ausdrückliche Rotation ist der
Recovery-Weg.

Im Ziel liefert Identity Calendar eine materialisierte Liste aktiver
Membership-ID-/Committee-ID-Paare.
Calendar beschränkt die Projektion auf diese aktiven IDs und Committees und
prüft den Scope vor Sync sowie erneut vor Event-/ICS-Ausgabe.
Damit zeigt ein Token nach Teilwiderruf keine Daten des deaktivierten
Committees, solange andere Mitgliedschaften aktiv sind.
Ein gültiges Feed-Token allein genügt ohne aktiven Identity-Scope weder für
Sync noch Ausgabe.
Zielverantwortung für Feed-Credentials, lokale Projektion und ICS-Ausgabe ist
ein eigenständiges `calendar`-Modul.
`integrations` bleibt konkreten externen Adaptern vorbehalten.
`notifications.service` besitzt Empfänger-, Ereignis- und Inhaltsregeln sowie
Retry-, Fallback- und Claim-Policy.
Es spricht über typisierte Repository-/UoW-Ports mit der Persistenz und über
einen Gateway-Port mit dem Provideradapter.
`integrations.notification_delivery` übersetzt SMTP- und WebPush-Ergebnisse in
ProviderOutcomes; der SQLite-Adapter liegt unter `persistence.notifications`.
Der Claim wird vor Provider-I/O committet.
Nur der weiterhin gültige, nicht abgelaufene Claim darf Ergebnis und
Abonnementinvalidierung speichern.
Ob Empfänger und fachliches Ereignis vor dem Versand erneut validiert werden,
bleibt als Entscheidung in #1079 offen.

`persistence.database` prüft Historienpräfix und Checksummen getrennt von
Backup, migrationsspezifischer Vorbereitung, SQL-Ausführung und Historiennachweis.
Diese Phasen bleiben unter derselben Migrationssperre; historische SQL-Skripte
behalten ihre eigenen Commit- und Rollbackgrenzen.
Der Prüfungsort-Preflight liest zunächst den Altbestand, leitet daraus Gruppen,
Konflikte und Berichte ab und veröffentlicht die Berichte vor dem SQL-Lauf.
Ein Konflikt bleibt damit diagnostizierbar, ohne die Migration zu beginnen.

`backend.fastapi_dependencies` stellt gemeinsame FastAPI-Dependencies
für Request-Kontext, Session, CSRF, aktive Mitgliedschaft, Betreiberzugriff
auf Prüfungsorte und Rundenzugriff bereit.
Die Handler deklarieren ihren bisherigen Sicherheitsvertrag über die
Kontext-Dependencies; fachliche Entscheidungen verbleiben in den vorhandenen
Autorisierungs-, Lifecycle- und Fachservices.
Ein Request teilt einen Kontext einschließlich der von der Runtime-Policy
gewählten Datenbank.
Die Transport-Middleware prüft nach Origin und OPTIONS die Body-Header vor
der Routerauswahl, ohne den Body einzulesen.
Nur Routen mit einem von FastAPI erkannten Request-Body puffern die ASGI-Daten
über `BoundedBodyRoute` inkrementell;
jeder Chunk wird vor dem Anhängen gegen die verbleibende Grenze geprüft.
Bei Überschreitung folgen ein geheimnisfreier 413-Fehler und keine weiteren
Receive-Aufrufe; ein Übertragungsabbruch verwirft den unvollständigen Body
mit einem festen 400-Fehler.
Die Grenze gilt auch ohne beziehungsweise bei zu kleinem `Content-Length`
und unabhängig vom Datenbank-Lifecycle.
Headerfehler bleiben vor Routing und Authentisierung;
die tatsächliche Größenprüfung folgt der Auswahl einer bodylesenden Route
und steht vor deren Authentisierung und Payloadverarbeitung.
Für `application/json` dekodiert FastAPI syntaktisches JSON unmittelbar nach
der Größenprüfung.
Ein Syntaxfehler ergibt deshalb vor den Route-Dependencies den festen,
geheimnisfreien Fehler `Invalid JSON body`.
Bei syntaktisch gültigen Daten laufen Authentisierung, CSRF, Actor sowie die
aus Route oder Rohvertrag bestimmbaren Scope-Prüfungen einschließlich Runtime-
und Lifecycle-Policy vor der Feldvalidierung des Request-Modells.
Muss der fachliche Scope erst aus einem typisierten Befehlsmodell abgeleitet
werden, folgt diese Prüfung der geheimnisfreien Modellvalidierung.
`RequestContext.read_json` bleibt als zentrale Kompatibilitätsgrenze für den
bisherigen JSON-Medientyp und den Object-Envelope sowie für Policies bestehen,
die den Rohvertrag vor der Pydantic-Feldvalidierung prüfen müssen.
Diese Wiederholung erzeugt kein zweites Request-Schema.
Normale Pfad- und Queryparameter sind typisiert an Route oder Dependency
deklariert.
Prüfungsort-IDs liegen ausschließlich in ihrer Access-Dependency, weil deren
bestehender Vertrag genau einen 422-Fehler vor der Authentisierung verlangt;
der Handler erhält den dort validierten Wert über `venue_identifier`.
Die ID im persönlichen Kalenderpfad bleibt absichtlich ein undurchsichtiger
String und bildet nicht numerische sowie unbekannte Werte einheitlich auf 404
ab.
GET, HEAD, unbekannte Routen und bodylose Aktionen lesen keinen Body.
Der lokale Unix-Socket-Adapter besitzt eine getrennte
Betreiberautorisierungsgrenze, verwendet aber dieselben Services,
Transaktionen und Repositories wie HTTP.
`AdminApplication` erhält den serverseitig ermittelten technischen Akteur,
Service-Factories und Persistenzpfade ausdrücklich vom jeweiligen Adapter.
Der Anwendungskern liest und schreibt keine globalen Prozessstreams;
Die Socket-Adapter sind die einzigen ausführbaren Betreibergrenzen des aktuellen
Backends; der Anwendungskern wird ausschließlich in der Backend-Assembly
komponiert.

`backend.admin_socket.AdminSocket` bindet den Kontrolltransport im selben Prozess
an HTTP und den injizierten Anwendungskern.
Die vorbereitende Assembly wird beim Start von `backend.server` mit
`--admin-socket-dir /run/lzug-admin --admin-socket-gid <betreiber-gid>`
ausdrücklich eingeschaltet.
Nach `RuntimeCoordinator.claim()` startet zuerst der Socket; anschließend läuft
die Initialisierung im HTTP-Lifespan, während beide Diagnosezugänge erreichbar sind.
Das Verzeichnis muss bereits existieren, dem effektiven Serverbenutzer und der
angegebenen Betreibergruppe gehören und exakt Modus `0750` haben.
Es liegt auf flüchtigem Speicher außerhalb von Datenbank, `/data`, Dokumenten,
Backups, Schlüsseln und Konfiguration.
Der Server erzeugt darin ausschließlich `admin.sock` mit Modus `0660`.
Das Produktimage liefert das `lzug-admin`-Binary zusammen mit dem Backend aus.
Die CLI spricht den bereitgestellten lokalen Admin-Socket;
die Image- und Compose-Konfiguration liegt bei der Betriebsanleitung und den
Containerverträgen.

Die Linux-Assembly öffnet jede Verzeichniskomponente ohne Symlinkauflösung,
verlangt vertrauenswürdige Eigentümer und verbietet schreibbare Vorfahren;
ein root-eigener Sticky-Vorfahr wie `/tmp` ist mit anschließendem privaten
Verzeichnis zulässig.
Ein gesperrter Verzeichnisdeskriptor hält die Bindungs- und Löschoperationen
unabhängig von Pfadumbenennungen am geprüften Verzeichnis.
Fremde Dateien und aktive Sockets bleiben erhalten.
Nur ein eigener Socket mit passenden Rechten und nachgewiesenem
`ECONNREFUSED` darf beim Start ersetzt werden.
Beim Stoppen wird nur der selbst erzeugte Socket-Inode entfernt.

Zusätzlich zu den Linux-Dateirechten prüft der Server `SO_PEERCRED`.
Zugelassen sind die Server-UID oder die konfigurierte **primäre** Betreiber-GID;
eine ausschließlich ergänzende Gruppenzugehörigkeit genügt nicht.
Ein Client kann seine Autorisierung nicht durch JSON-Akteursangaben erweitern.
Die Listener-Assembly ist Linux-spezifisch; ohne aktivierten Socket bleibt der
bestehende Serverstart auch auf den Entwicklungsplattformen verwendbar.
Die Betriebssystemgrundlage erläutert [unix(7)](https://man7.org/linux/man-pages/man7/unix.7.html).

Der Kontrollvertrag verwendet vier Byte vorzeichenlose Big-Endian-Länge und
anschließend genau ein UTF-8-JSON-Objekt je Frame.
Vor jedem Auftrag sendet der Client `{"type":"hello","protocol":1,"schema":1}`.
`schema` bezeichnet das Admin-Auftragsschema, nicht den SQLite-Migrationsstand.
Erst die passende Serverantwort erlaubt das Senden des bestehenden
`BackendRequest`; Protokoll-/Schemaabweichungen beenden die Verbindung vor
fachlicher Ausführung.
Die Antwort enthält eine serverseitige Auftrags- und Korrelations-ID.
Es folgt genau ein Kontrollauftrag und ein `result`-Frame mit unveränderter
Anwendungskern-Antwort und Exitcode oder ein geheimnisfreier `error`-Frame.
Weitere Aufträge auf derselben Verbindung werden nicht ausgeführt.
Upgrade und Rollback bleiben in dieser Assembly gesperrt.

`SocketTransport` und `SocketRuntimeFactory` implementieren in der Go-CLI die
vorhandenen injizierbaren Transportschnittstellen für Kontrollaufträge und Artefakte.
Der Pfad wird der Factory ausdrücklich übergeben; sie startet keinen Prozess
und kennt weder Transportfallback noch automatische Wiederholung.
`TargetRuntimeFactory` bindet diese Aufträge über die expliziten Zieloptionen
auch an die gemeinsame direkte und interaktive CLI an.
Imagewechsel und Containerstart bleiben Aufgaben der Containerplattform.
Die CLI führt sie nicht selbst aus und verwendet für den laufenden Backendprozess
den bereitgestellten Admin-Socket.

Der Listener begrenzt gleichzeitig aktive Verbindungen standardmäßig auf acht,
Handshake auf fünf Sekunden, Auftrag einschließlich Ergebnisübertragung auf
30 Sekunden und Shutdown-Drain auf 30 Sekunden.
Die Serveroptionen `--admin-socket-connections`,
`--admin-socket-handshake-timeout`, `--admin-socket-request-timeout` und
`--admin-socket-shutdown-timeout` setzen diese Grenzen ausdrücklich.
Eingehende Kontrollaufträge sind auf 64 KiB, Ergebnisframes auf 1 MiB begrenzt.
Teileingaben verlängern keine Deadline; zusätzliche Verbindungen werden ohne
Warteschlange von Anwendungsaufträgen geschlossen.
Eine bereits zugelassene Mutation behält auch nach Timeout oder Verbindungsabbruch
ihren Worker und ihre Runtime-Zulassung bis zum Ende.
Ein Drain-Timeout gibt weder den Verzeichnislock noch die Runtime-Ownership frei.
Der HTTP-Lifespan beendet deshalb zuerst den Socket samt seinen Workern und gibt
erst danach die Runtime-Ownership frei; dies gilt auch für Diagnoseaufträge ohne
eigene Runtime-Zulassung.
Listenerfehler schließen die normale Runtime-Zulassung und starten keinen Ersatzprozess.

Artefaktaufträge verwenden denselben Handshake und dieselben serverseitigen IDs.
`backend.admin_socket_artifacts` bindet den bestehenden `ClearArtifactService`
an diesen Transport; die Go-Factory stellt dafür `ArtifactTransport` bereit.
Ein `stream-ready`-Kontrollframe bestätigt Richtung und effektive Transfergrenzen,
bevor Klartextpaketdaten gesendet werden.
Das höchste Bit des vier Byte langen Frame-Headers kennzeichnet Binärdaten;
die übrigen Bits geben deren Länge an.
Ein Datenframe enthält höchstens 64 KiB; Kontrollframes sind weiterhin JSON.
Der Transport hält jeweils nur einen Datenframe und verwendet synchrone,
durch die Socketpuffer gebremste Schreibzugriffe ohne Anwendungswarteschlange.

Ein `stream-end`-Kontrollframe enthält Bytezahl und SHA-256 des gesamten Streams.
Beim Upload muss danach der Schreibkanal des Clients geschlossen sein;
EOF ohne passenden Abschluss, zusätzliche Bytes oder fehlerhafte age-Integrität
erlauben keine Paketprüfung und keinen Restore.
Die CLI sendet diesen Abschluss erst nach authentifiziertem EOF ihres lokalen
age-Lesers; private age-Identitäten bleiben ausschließlich dort.
Beim Download veröffentlicht die CLI ihr verschlüsseltes temporäres Ziel erst
nach passendem Streamabschluss, erfolgreichem Ergebnis und Verbindungsende.
Fehler und Teilübertragungen veröffentlichen kein Zielartefakt.

Es läuft höchstens ein Artefaktauftrag gleichzeitig; weitere werden mit
`artifact_busy` ohne Warteschlange zurückgewiesen.
Diagnose- und Kontrollverbindungen behalten ihre eigenen Verbindungsslots.
`--admin-socket-max-stream-bytes` begrenzt den Transfer auf höchstens 1 GiB
und kann diese Grenze absenken.
`--admin-socket-stream-timeout` setzt die absolute Transferfrist,
standardmäßig 300 Sekunden und höchstens eine Stunde; Teilframes verlängern sie nicht.
Die Paketaufbereitung begrenzt zusätzlich SQLite-Kopien auf 64 MiB,
JSON-Metadaten und ZIP-Zentralverzeichnis auf je 8 MiB und die ZIP-Einträge auf 4096.
Komprimierte oder ZIP64-Eingabepakete werden am Socket abgewiesen.
Der Klartextupload und seine entpackten Inhalte überschreiten jeweils das Transferlimit nicht;
Restore benötigt zusätzlich eine vorbereitete Kopie und gegebenenfalls eine Migrationssicherung.
SQLite-Verbindungen in dieser temporären Restore-Kopie erhalten eine Seitengrenze.
Die Paketmetadaten bleiben begrenzt materialisiert; das vollständige Paket wird
weder in Go noch im Socketadapter im Arbeitsspeicher gesammelt.

Temporäre Klartextdateien liegen in privaten Backendverzeichnissen;
ihre Bereinigung erfolgt vor Freigabe des Artefaktslots.
Ein Bereinigungsfehler wird als `artifact_cleanup_failed` diagnostiziert.
Danach bleibt die Artefaktzulassung dieses Listeners gesperrt,
damit weitere Aufträge keine zusätzlichen temporären Reste ansammeln.
Der Betreiber prüft und bereinigt die Reste, bevor er den Prozess erneut startet.
Ein langsamer Upload hält noch keine exklusive Runtime-Zulassung.
Nach vollständigem Empfang verwendet Restore die bestehende exklusive
Runtime- und Aktivierungsgrenze; konkurrierende HTTP-Aufträge und Lifecycleoperationen
folgen damit derselben Konfliktordnung.
Eine zugelassene Ausführung wird bei Verbindungsverlust zu Ende geführt,
ohne automatische Wiederholung oder vorzeitige Freigabe ihrer Sperren.
Die Go-Aufrufer besitzen ihre lokalen Reader/Writer und müssen deren blockierende
Datei- beziehungsweise Pipe-Zugriffe selbst abbrechbar halten;
der Adapter erzeugt dafür keine zurückbleibenden I/O-Goroutinen.

`config`, `status` und `doctor` enthalten neben dem Runtime-Snapshot den
geheimnisfreien Socketzustand und die effektiven Limits.
Der Kontrollauftrag `socket-job-status` mit `arguments: {"job_id":"<uuid>"}`
ermittelt den technischen Zustand eines zuvor angekündigten Auftrags.
Der begrenzte Speicher hält 128 Aufträge mit Befehlsklasse, Phase, Status und
Übertragungszustand, ohne Argumente, fachliche Ergebnisse oder Tokens.
Nach Verdrängung oder Prozessneustart lautet der Zustand `unknown`;
das ist kein Nachweis für eine unterbliebene Ausführung.
`delivery: sent` belegt nur die Übergabe an den Kernel, keinen Empfang beim Client.
Ein Ergebnisverlust erlaubt daher keine automatische Wiederholung.
Auditereignisse enthalten ausschließlich verifizierte technische Identität,
Befehlsklasse, Beginn/Ende, Fehlerphase, Status und die beiden IDs.

`backend.tests.test_admin_socket` prüft echte Linux-Sockets einschließlich des
Go-Adapters, negativer Dateisystem-/Peer-Fälle, Handshake, Abbruch und Shutdown.
`backend.tests.test_admin_socket_artifacts` ergänzt begrenzte und fortlaufende
Streams, fehlerhafte Abschlussgrenzen, Rückstau, Abbruch, Ergebnisverlust und
den echten Go-age-Rundlauf für Backup, Export, Prüfung und Restore.
Der Backend-CI-Lauf installiert dafür auch die gepinnte Go-Toolchain.
Tests mit echten UID-/GID-Wechseln benötigen zusätzlich einen isolierten
Linux-Testcontainer mit root; sie verändern nur dessen temporäre Testverzeichnisse.

`backend.runtime.RuntimeCoordinator` besitzt im Serverprozess die
Runtimezustände, Auftragszulassung und Start-/Stoppkoordination.
Die HTTP-Assembly und ein injizierter `AdminApplication`-Kern verwenden denselben
Koordinator; Services finden ihn über den kanonischen Datenbankpfad.
Ein Prozess-Lock verhindert einen zweiten Server für diese Datenbank.
Ein Auftrag hält seine Zulassung über alle Servicetransaktionen hinweg;
jede Persistenztransaktion hält zusätzlich eine eigene Zulassung bis zum
Schließen ihrer Verbindung.
Dadurch kann ein abgebrochener HTTP-Aufruf keinen noch arbeitenden Worker
vorzeitig aus der Stopp- oder Wartungskoordination entlassen.

Restore und Migration schließen zuerst die Zulassung neuer Fachaufträge,
warten auf bereits zugelassene Arbeit und führen anschließend exklusiv aus.
Ein konkurrierender Wartungsauftrag wird abgewiesen; es gibt keine implizite
Warteschlange oder automatische Wiederholung.
Die Sperrordnung lautet Zulassung, Aktivierung, Snapshot und Migration.
Snapshot und Migration verwenden auch im bisherigen separaten
Kompatibilitätsadapter dieselben Dateisperren wie die Fachtransaktionen.

Der interne Diagnose-Snapshot liest weder SQLite noch Dokumente.
Der atomar geschriebene Sidecar `<datenbank>.runtime-job.json` hält ausschließlich
ID, Klasse, Status und Wiederherstellungsbedarf des letzten exklusiven Auftrags fest.
Er enthält keine Argumente, Ergebnisse oder Fehlertexte und gehört zusammen
mit den dauerhaft bestehen bleibenden Lockdateien zur Instanz.
Nach einem unterbrochenen oder fehlgeschlagenen Auftrag bleibt der Wiederanlauf
gesperrt, bis eine ausdrücklich angestoßene Wiederherstellung erfolgreich
geprüft wurde; der Koordinator wiederholt den Auftrag nicht.
Ein noch wartender Auftrag kann abgebrochen werden.
Ein laufender Auftrag beendet seine Arbeit unter den gehaltenen Sperren.
Ein Stopp-Timeout lässt die Ownership bestehen und erlaubt keinen parallelen
Ersatzprozess.

`backend.server --init` initialisiert ausschließlich leere Datenbestände.
Ein vorhandenes Schema mit Migrationsbedarf bleibt live/not-ready und sperrt
Fachaufträge bis zur ausdrücklichen Freigabe über `lzug-admin upgrade apply`.
`upgrade status` liest den gecachten Schema- und Buildstand und weist
Freigabepfad, Backupanforderung und Restoregrenze aus.
Der Socket prüft das lokal entschlüsselte Paket gegen den im selben Prozess
angelegten Sicherungsnachweis; Clientbehauptungen ersetzen keine Paketprüfung.
Eine Migration hält die exklusive Runtime-Sperre und verwendet die
Socket-Auftrags-ID auch für das dauerhafte Runtime-Journal.
Nach Fehler oder unterbrochenem Auftrag bleibt die Runtime gesperrt;
Verbindungsverlust und Neustart wiederholen keine Mutation.
Ready und Fachzulassung werden erst nach erfolgreicher Nachprüfung und
persistiertem Auftragsabschluss freigegeben.
Die öffentliche HTTP-/Frontenddarstellung verwendet denselben Snapshot.
Imagewechsel und Containerstart bleiben gemäß
[ADR-0033](decisions/0033-aio-betrieb-admintransport-und-lifecycle.md)
bei der Containerplattform.
Das [Betreiberverfahren](https://github.com/lxndrp/lzug/wiki/Administration-Update-und-Rollback)
beschreibt Freigabe und Wiederherstellungsgrenzen.

Die folgende Tabelle ist die kanonische knappe Zuordnung der aktuellen
Backend-Paketstruktur.
Abhängigkeiten verlaufen nur in die genannten Zielpakete; der automatisierte
Architekturtest verhindert nicht zugeordnete Module, unerlaubte Richtungen und
Zyklen zwischen den zehn Kernpaketen.

| Paket | Verantwortung | Darf abhängen von |
| --- | --- | --- |
| `application/` | frameworkneutrale Use-Case-Orchestrierung, Ressourcenfassade, Transportobjekte und HATEOAS | `assessment`, `execution`, `identity`, `integrations`, `notifications`, `operations`, `persistence`, `planning` |
| `planning/` | Planaggregate, mögliche Prüfungstage, Prüfungsorte und Folgen bestätigter Änderungen; Kandidatentage beginnen mit einem adapterfreien Port-Pilot | `integrations`, `notifications`, `persistence` (Legacy-Aufrufe) |
| `execution/` | Ausfall und Ersatz, Protokolle, Tagesabschluss und Rundenlebenszyklus | `identity`, `integrations`, `notifications`, `persistence` |
| `assessment/` | individuelle Bewertungen und festgestellte Ergebnisse | `execution`, `identity`, `persistence` |
| `identity/` | Authentisierung, Autorisierung, Mitgliedschaften und lokale Betreiberidentität | keine anderen Kernpakete |
| `integrations/` | Kalender (Übergangspfad), Dokumentablage, Feiertage, Kartenanbieter und künftige externe Adapter | `identity`, `notifications`, `persistence` |
| `notifications/` | Benachrichtigungsregeln, Zustellpolicy sowie Provider- und Persistenzports | keine anderen Kernpakete |
| `persistence/` | Modelle, Datenbank, Migrationen und niedrige Store-Primitive | `identity`, `notifications` |
| `operations/` | Backup und Export, Empfängerverwaltung, Diagnose und Lifecycle | `identity`, `integrations`, `persistence` |

Der Paketroot enthält ausschließlich gemeinsame Runtime-Verträge und die
stabilen äußeren Einstiege für FastAPI, Prozessstart, Healthcheck und
Admintransport.
Die weitere Gliederung der HTTP-Schicht unter `api/` bleibt #646 vorbehalten.

Neue Fachregeln beginnen in einem Service und seinen fokussierten Tests.
Die Ressourcenfassade kapselt fachnahe Persistenzzugriffe; Adapter übersetzen HTTP,
Dateien, Kalender oder Zustellkanäle.
Eine neue Speicher- oder Transporttechnik darf die Invarianten weder kopieren
noch umgehen.
Nur der autoritative Backendprozess greift schreibend auf SQLite und `/data` zu.
Er hält während Initialisierung, Wartung und Migration den Admin-Socket für
zulässige Status-, Diagnose- und Freigabeaufträge erreichbar, bleibt live und
meldet erst nach vollständiger Betriebsbereitschaft ready.

Die kanonische Runtime-Konfigurationsassembly liegt in
`backend/src/backend/settings.py`.
Die Betreiberreferenz beschreibt ausschließlich die von außen sichtbaren
Variablennamen, Defaults und Betriebsfolgen und dupliziert keine
Validierungslogik.

Die [Python-Referenz](reference/backend.md) wird aus den öffentlichen
Google-Style-Docstrings erzeugt.
OpenAPI entsteht ausschließlich über die unveränderte FastAPI-Erzeugung aus
Anwendung, Dependencies, Response-Modellen und den an den Operationen
hinterlegten Pydantic-Schemata.
`backend.fastapi_assembly` exportiert getrennte Publikations- und
Transportprofile; lokale Builds, CI und OCI-Builds exportieren das
Transportprofil aus demselben Checkout und generieren daraus vor Angular mit
`openapi-ts` die versionierten Frontend-Typen.
`backend.version` vereint Runtime-Zugriff, Modell und CLI-Export der
kanonischen Build-Identität für CLI- und Containerverbraucher.
Der CLI-Export verlangt Revision und optionalen Tag ausdrücklich.
Git-Revisionen und annotierte Tagziele werden vor diesem Komponentenaufruf
durch Git oder den jeweiligen Aufrufer geprüft.
Beides ergänzt die Komponentenorientierung, ersetzt aber nicht Service- und
Vertragstests.

## Optionale Kartenanbieter

Die Kartenintegration ist ausschließlich geschützte Deployment-Konfiguration
des Betreibers, nicht Teil der Produktoberfläche.
`LZUG_MAP_PROVIDER` ist standardmäßig `off` und erlaubt nur `off`, `osm` oder
`google`.
Aktive Modi verlangen `LZUG_NOMINATIM_USER_AGENT`; ein abweichender
`LZUG_NOMINATIM_URL` muss ein HTTPS-Endpunkt sein.
Der Google-Modus prüft zusätzlich einen passend eingeschränkten
`LZUG_GOOGLE_MAPS_API_KEY`.
Ein Google Maps Embed API Browser-Key ist technisch kein Geheimnis, weil Google
ihn im Iframe-URL erhält.
Er wird daher ausschließlich als nicht sichtbares Attribut der ohnehin
geladenen HTML-Shell an den Browser gegeben und muss auf die produktiven
Referrer sowie die Maps Embed API beschränkt sein.
Er erscheint weder in JSON-/OpenAPI-Antworten, Diagnosen, Logs noch als
Produktoberflächentext; andere Zugangswerte werden nicht ausgeliefert.
`lzug-admin system config` prüft nur die geheimnisfreie Gültigkeit.

Nur die Ortsdetailansicht lädt eine Karte und zeigt die providerseitige
Attribution.
Ein bewusster externer Wechsel übergibt ausschließlich bestätigte
Zielkoordinaten.
Die öffentliche Demo ist für eine spätere freigegebene Auslieferung fest auf
OpenStreetMap konfiguriert.
Das Iframe lädt Kacheln erst beim Öffnen eines Ortsdetails; Übersichts-,
Vorab- und Offline-Downloads finden nicht statt.
Browser-Caching und ein gültiger Referrer bleiben entsprechend der
OpenStreetMap-Tile-Policy erhalten.
Vor dem Iframe erklärt die Oberfläche, dass Browser- und Anfragedaten direkt an
OpenStreetMap-Infrastruktur übertragen werden können.
Schlägt der Provider fehl, bleiben alle Ortsdaten und der bewusst auslösbare
externe Ziellink nutzbar.
Nominatim wird ohne Autocomplete und ohne Wiederholung nur für eine
ausdrücklich ausgelöste Positionsprüfung aufgerufen.
Die Antwort wird auf Koordinaten und Herkunft reduziert, bevor ein
berechtigtes Ausschussmitglied oder ein Betreiber sie bestätigt.

Koordinaten bleiben anbieterneutral gespeichert.
Eine Adressänderung erhält die bisherige Position, markiert sie aber als
`needs_review`.
Bei aktivem Anbieter sind neue Planungen bis zur Bestätigung gesperrt.
Provider-, Quoten- und Timeoutfehler verändern keine Fachdaten und enthalten
in der Diagnose nur Anbieter und Fehlerklasse.

## Frontend

### Frontend-Zielvertrag

Datenbesitz, Schreibrechte, Featuregrenzen, Zustandslebensdauern und Übergänge
sind im [Frontend-Architekturvertrag](frontend-architecture-contract.md)
verbindlich beschrieben.
Die langfristige Entscheidung steht in
[ADR-0042](decisions/0042-frontend-zustandsbesitz-und-feature-lebensdauern.md).
Die folgenden Abschnitte beschreiben weiterhin die vorhandene Angular- und
REST-Komponentenstruktur.

Das Angular-Frontend verwendet TypeScript, Angular Router und Taiga UI.
Es ist ein ruhiges Arbeitswerkzeug für wiederkehrende Ausschussprozesse und
keine Marketingoberfläche.
Die Zielabhängigkeit verläuft von Komponenten über Feature-Facades und
Anwendungsfälle zu Ports; Adapter binden HTTP, Browserfunktionen und weitere
Integrationen an.
Fachliche API-Clients unter `frontend/src/app/api/` kapseln heute den
Backendtransport.
`ApiClient` besitzt den gemeinsamen HTTP- und Collection-Transport;
Planung, Stammdaten, Prüfungsrunden, bestätigte Pläne, Prüfungstage,
Prüfungsprotokolle, Ergebnisse, persönliche Daten und Prüfungsorte besitzen
jeweils einen fachlichen Client.
Der schmale `api.models.ts`-Export hält bestehende Importpfade stabil, ohne
Transportmodelle erneut zu definieren.
Komponenten konsumieren nur die Facade ihres Features oder ausdrücklich
UI-nahe gemeinsame Services.
Facades stellen die Zustände und Befehle bereit, die eine Oberfläche benötigt;
Anwendungsfälle koordinieren fachliche Abläufe und hängen von Ports ab.
Ports benennen die benötigten Fähigkeiten ohne HTTP-Pfade, Statuscodes oder
OpenAPI-Typen.
Adapter übersetzen zwischen solchen Verträgen und konkreten technischen
Schnittstellen.
`app.config.ts` ist die Composition Root für anwendungsweite Adapterwahl.
Eine lokale Feature-Registrierung ist passend, wenn ein Adapter nur zu einem
Feature gehört.

Diese Grenze wird schrittweise featureweise eingeführt.
Die Terminübersicht unter `frontend/src/app/scheduling-overview/` zeigt das
Muster: Ihre Komponente verwendet `SchedulingOverviewFacade`, der
Anwendungsfall hängt am `SchedulingOverviewPort`, und
`HttpSchedulingOverviewAdapter` übersetzt das vorhandene API-Modell in ein
transportneutrales Featuremodell.
Die bestehende Anzeige und ihre Lade-, Leer- und Fehlerzustände bleiben dabei
unverändert; ihre Komponententests benötigen keinen HTTP-Testcontroller.
Der Architekturtest prüft die Abhängigkeiten dieses Beispiels.
Weitere direkte API-Abhängigkeiten werden mit der Migrationsplanung #907
umgestellt.

Abstraktionen entstehen nur an einer tatsächlichen Austausch- oder
Testgrenze.
Eine Facade oder ein Use Case ist keine Pflichtklasse pro API-Aufruf.
OpenAPI-generierte Typen und Transportdetails bleiben langfristig im jeweiligen
HTTP-Adapter; die konkrete Bereinigung der vorhandenen API-Modelle und
HTTP-Fehlergrenzen ist in #908 nachgewiesen.

`DashboardProjectionService` besitzt den Dashboard-Read einschließlich seines
Lade- und Fehlerzustands; `HttpDashboardProjectionAdapter` lädt nur Runde,
Summary und Board.
`ApplicationShellContextService` lädt Version sowie kompakte Halbjahr-,
Runden- und Ausschusslabels separat.
Kandidaten- und Ausschussansichten laden über eigene Methoden des
`MasterDataPort`; deren Fehler und Invalidierung bleiben voneinander getrennt.
`ApplicationWorkspaceService` hält befristet den Planungs-/Halbjahres-
Kompatibilitätszustand hinter `WorkspacePort`.
Nach Venue-/Raumänderungen werden die Dashboard- und Legacy-Board-Ortsreferenzen
mit gezielten `/api/locations`-Reads aktualisiert; die übrigen Workspace- und
Dashboarddaten bleiben erhalten.
Bestätigte Pläne und Prüfungstage lesen ihre Ortsangaben über eigene
API-Projektionen, sobald ihre Route geöffnet wird; sie halten keine globale
Ortskopie über einen Routenwechsel hinweg.
Die Ortsroute lädt über `LOCATIONS_READ_PORT` und den
`HttpLocationsReadAdapter` direkt `/api/exam-venues`.
`LocationsWorkspaceFacade` hält Lade-, Fehler- und Snapshotzustand
routegebunden; Ortscommands lösen keinen vollständigen Workspace-Refresh aus.
Die Ortsantwort enthält den Namen des zuständigen Ausschusses als schmale
Referenz, damit Operatoren für freigegebene Orte keinen Ausschuss-Read benötigen.
Mitgliedsansichten laden die Liste für den Anlege-Selektor ergänzend und
veröffentlichen Ortsdaten schon vor deren Abschluss.
Ein später erfolgreicher Ortscommand aktualisiert die gerade aktive Ortsansicht;
Draft-Effekte bleiben an ihre ursprüngliche Ansicht gebunden.
`PlanningWorkflowService` koordiniert Planungsbefehle über `PlanningPort`;
`HttpPlanningAdapter` übersetzt diese Aufrufe in den vorhandenen API-Client.
Vorschlagserzeugung und Vorschlagsspeicherung sind dabei persistierende
Planning-Commands; die Leseoperation für den gespeicherten Vorschlag bleibt
getrennt.
Einstellungen, Verfügbarkeiten, Vorschauerzeugung und erstmalige Bestätigung
nehmen keine Quellrevision entgegen.
`savePlanningProposal()` erhält dagegen die Revision des geladenen Vorschlags
und übermittelt sie unverändert für die optimistische Sperre.
Prüfungstag-Anwesenheit übergibt Slot-ID für Prüflinge beziehungsweise
Assignment-ID für Ausschussmitglieder sowie die vom Befehl akzeptierte
Tagesrevision.
`ExamDayFacade` besitzt Tagesread, Lade-/Fehlerzustand, angenommene Commands
und bestätigte Antworten für die Lebensdauer der Prüfungstagsansicht;
die reine `ExamDayApplication`-Weiterleitung entfällt.
Die Komponente behält ihre Formularentwürfe und Darstellung. Ein Refresh im
gleichen Runden-/Tageskontext übernimmt neue Serverwerte in unveränderte Drafts,
bewahrt davon abweichende lokale Drafts und löscht Drafts entfernter Einträge.
Ein Wechsel von Runde oder Tag verwirft alle Tages-Drafts.
Protokoll und Ergebnis erhalten Runde, Tag, Slot und Tagesrevision explizit;
ihre erfolgreichen Änderungen melden Tagesrevisionen über Outputs zurück,
damit Prüfungstag den bestätigten Tagesread und beide Kindreads gezielt
aktualisiert.
Während dieser Tagesrefresh läuft, bleibt der bestätigte Snapshot verborgen
gemountet, damit bereits angenommene Kindcommands ihre verzögerten Antworten
weiter an Protokoll oder Ergebnis zurückmelden können. Fehler dieser Commands
werden währenddessen am Prüfungstag sichtbar gehalten. Neue Kindcommands bleiben
bis zur geladenen Tagesrevision gesperrt.
Ein Wechsel nur der Tagesrevision lädt Protokoll und Ergebnis neu, ändert aber
nicht die Fence eines bereits angenommenen Commands; dessen Antwort kann einen
Versionskonflikt weiterhin im Ursprungskontext anzeigen. Ein Wechsel von Runde,
Tag oder Slot invalidiert dagegen den Commandkontext. Ergebnisstimmen bleiben
bei einer reinen Tagesrevision im lokalen Entwurf erhalten. Abweichende lokale
Protokollentwürfe, Vorbehaltstexte und Ergebnis-Punkteentwürfe überstehen
denselben Reload.
Session- und Ansichtswechsel verhindern, dass verspätete Antworten geschützten
Zustand einer neuen Ansicht verändern.
Bestätigte Pläne verwenden denselben Schnitt: `ConfirmedPlansWorkflowService`
ruft `ConfirmedPlansPort` auf, dessen HTTP-Adapter Plan- und Revisionsantworten
von HAL-Links bereinigt.
Planungs-, Stammdaten- und Ortsbefehle liegen in den zuständigen
Workflow-Services.
Die Verwaltung der Prüfungshalbjahre verwendet eigene Featuremodelle und den
`ExamHalfYearsWorkflowService`; `HttpExamHalfYearsAdapter` übersetzt
Runden- und Lebenszyklusverträge einschließlich der Nachweisexporte an der
HTTP-Grenze.
`App` besitzt nur Rahmen, Authentisierung, globale Runtimezustände,
Navigationsdarstellung und die gemeinsame Zugriffsansicht.
Die Hauptpfade in `app.routes.ts` aktivieren über `loadComponent` jeweils einen
eigenen Feature-Einstieg unter `frontend/src/app/routes/` oder eine bereits
eigenständige Fachkomponente.
Diese Einstiege binden Routeparameter und Feature-Ereignisse an den zuständigen
Kontext beziehungsweise Workflow; die Shell interpretiert keine URL-Segmente
und rendert Fachbereiche ausschließlich im `router-outlet`.

`RoundContextService` hält den aktuellen Prüfungsrundenkontext.
Dashboard, Stammdaten, Planung, Durchführung und Nachweise bleiben fachlich
erkennbare Bereiche.
Der Entwicklungsproxy leitet `/api` an das lokale Backend weiter; produktiv
werden Browser-Bundle und API same-origin aus dem OCI-Image bereitgestellt.

Der Produktionsbuild wurde für die Routingumstellung mit Node.js 26.5.0 und
`CI=true npm run build:ci` gegen die Ausgangsrevision
`cdf6849517e31c4858c74bfd08d1873de2c2eeda` und denselben Abhängigkeiten
verglichen.
Vor der Umstellung bestand der Initialbestand aus 1,27 MB Rohgröße bei einer
geschätzten Übertragungsgröße von 252,70 kB und besaß keine Feature-Chunks.
Mit den Routeneinstiegen beträgt er 661,50 kB beziehungsweise 158,06 kB.
Authentisierung, Dashboard, Planung, Prüfungsplan, Prüfungstag, Stammdaten,
Orte, Benachrichtigungen, Ausfall und Demo werden erst beim ersten Aufruf ihres
Pfads geladen; die ausgewiesenen Feature-Chunks liegen zwischen 6,70 kB und
96,18 kB Rohgröße.

Für sichtbare Änderungen gelten diese Komponentenregeln:

- Fachaufgabe, aktueller Zustand und Folgen einer Aktion müssen ohne
  Implementierungswissen verständlich sein.
- Laden, Leerzustand, Erfolg, Fehler, Bestätigung und Abbruch gehören zum
  betroffenen Ablauf.
- Primäre, sekundäre und destruktive Aktionen bleiben visuell und semantisch
  unterscheidbar.
- Desktop und Mobil sowie helles und dunkles Farbschema werden auf Fokus,
  Kontrast, Umbruch, Überlauf und erreichbare Aktionen geprüft.
- Taiga UI bleibt Komponenten- und Tokenbasis; zusätzliche Frameworks oder ein
  paralleles lokales Designsystem benötigen eine eigene begründete Entscheidung.

Der globale Frontend-Stylebestand in `frontend/src/styles.scss` enthält nur
Tokens, Reset/Basisregeln und wenige gemeinsame Layout-, Formular- und
Tabellenprimitive.
Fach- und seitenspezifische Regeln gehören in das Stylesheet der zuständigen
Angular-Komponente.
Responsive Regeln verwenden grundsätzlich `30rem` für schmale Inhalte,
`48rem` für kompakte Layouts und `75rem` für breite Grids.

[WCAG 2.2](https://www.w3.org/TR/WCAG22/) ist der Maßstab für
Zugänglichkeit.
Automatisierte Accessibility-Prüfungen decken nur messbare Teile ab;
Informationshierarchie, Begriffe, Fehlervermeidung und Aufgabenerfolg benötigen
zusätzlich ein sichtbares Review.
Die [TypeScript-Referenz](reference/frontend.md) entsteht aus TSDoc und wird im
Dokumentationsartefakt von TypeDoc ersetzt.

## Betreiber-CLI

`lzug-admin` ist eine portable Go-CLI für Linux, macOS und Windows auf amd64 und
arm64.
Sie wird als Betreiberartefakt getrennt vom Python- und Frontend-Produktimage
ausgeliefert.
Eine statische Registry ordnet jeden Command nach dem Muster
`lzug-admin <objekt> <aktion>` ein und ist die gemeinsame Quelle für Parser,
Hilfe, Completion und die
[generierte Befehlsreferenz](reference/cli.md).
Explizite Konstruktorverdrahtung verbindet Registry, Konfiguration, sichere
Eingabe, Renderer und Socket-Zugriff ohne IoC-Framework,
Service Locator, Reflection oder versteckte Registrierung.

Die CLI verbindet sich mit einem bereitgestellten lokalen Socket-Endpunkt.
`TargetRuntimeFactory` verwendet dafür `unix:///pfad` oder einen numerischen
Loopback-Endpunkt (`tcp://127.0.0.1:PORT`, `tcp://[::1]:PORT`).
Client und Backend kennen den Socket-Zugriff und den versionierten Adminvertrag;
die Bereitstellung des Endpunkts liegt außerhalb ihrer Zuständigkeit.
Kleine Aufträge und Antworten sind genau ein UTF-8-JSON-Objekt;
Artefaktoperationen trennen den potenziell großen Binärstrom von der
strukturierten Kontrollantwort.
Command-Handler greifen weder direkt auf Persistenz zu noch kennen sie
die Bereitstellung des Endpunkts.
Jeder Auftrag erhält eine eigene begrenzte Verbindung und einen Admin-Handshake
vor der fachlichen Übertragung.
Die interaktive Sitzung hält ihre Zielkonfiguration bis zum ausdrücklichen
Zielwechsel stabil; Verbindungsverluste lösen keine automatische Wiederholung aus.
Die CLI schließt ausschließlich eigene Verbindungen und verändert keine
bereitgestellten Listener oder Socketpfade.
Tests prüfen diese Socket-Eigenschaften und den gemeinsamen Adminvertrag.
Externe Transportwege sind weder Teil des Anwendungsvertrags noch der Testabnahme.
Die [Betriebsanleitung](https://github.com/lxndrp/lzug/wiki/Administration-Installation-und-Konfiguration#socketzugriff)
beschreibt die Endpunktkonfiguration und ein optionales Bereitstellungsbeispiel.
Die Betriebsanleitung beschreibt die Endpunktkonfiguration sowie die
Bereitstellung des passenden CLI-Binaries im Produktimage.

Die Befehlsgruppen umfassen:

- lokale, geheimnisfreie Diagnose mit `status`, `config` und `doctor`;
- Konto- und Ausschussverwaltung ohne fachliches Leserecht;
- Benachrichtigungs- und Planfolgenverarbeitung;
- geschützte Backups, nicht mutierende Prüfung, vollständigen Restore und
  geschützten Vollexport;
- releasegebundenes Upgrade und nicht mutierende Rollback-Freigabe in einem
  live, aber nicht ready befindlichen Backendprozess.

Private age-Identitäten werden ausschließlich lokal aus einer geschützten
Datei, ausdrücklich gewähltem `stdin` oder am TTY ohne Echo gelesen.
Sie erreichen den Backendtransport nicht.
Einmaltoken werden über den bisherigen sicheren stdin-Kanal übertragen.
Beide Geheimnistypen sind als Argument, Konfiguration oder Umgebungswert
ausgeschlossen.
Gewöhnlich destruktive Commands benötigen am Terminal eine konkrete Rückfrage;
ohne TTY ist vor jedem mutierenden Transportaufruf `--force` erforderlich.
Ein Restore auf nicht leerem Ziel und irreversible Migrationen behalten ihre
separaten semantischen Bestätigungen, die `--force` nicht ersetzt.

Human-Ausgabe ist standardmäßig still und gibt nur erforderliche einmalige
Werte oder ausdrücklich abgefragte Diagnose aus.
`--verbose` ergänzt geheimnisfreie Details auf `stderr`.
`--json` liefert bei Erfolg und Fehler genau ein Objekt mit Schema- und
Protokollversion, Fehlerklasse und Exit Code auf `stdout`; ungeprüfte
Backendtexte und Engine-Diagnose werden nicht durchgereicht.
Nicht geheime Zielprofile enthalten den lokalen Socket-Endpunkt und einen
optionalen Anzeigenamen.
Explizite Parameter, Umgebung, optionale JSON-Datei und Standardwerte behalten
ihre dokumentierte Priorität.
`lzug-admin config inspect` zeigt effektive geheimnisfreie Werte und ihre
Herkunft, ohne Konfiguration zu verändern.

`lzug-admin cli` ist ein zeilenorientierter Adapter auf dieselbe Registry.
Er erzeugt Objekt- und Aktionsnavigation, Suche, Eingabeschritte und Hilfe aus
den Command-Metadaten und ruft danach denselben `Application.Execute`-Pfad wie
die direkte Syntax auf.
Damit bleiben Argumentschema, vollständige Validierung, Request Builder,
Transport, Secret-Eingabe und Ergebnisrenderer eine gemeinsame
Implementierung.
Der Dialog prüft sein Sitzungsziel vor dem ersten backendabhängigen Command;
lokale Commands bleiben auch ohne erreichbares Ziel nutzbar.

Die Dialogoberfläche benötigt interaktive Ein- und Ausgabe-Terminals und
verwendet linearen Text ohne Vollbild-Neuzeichnung.
Sie speichert weder Dialogzustand noch Eingaben, Geheimnisse oder
Bestätigungen.
Geheimnisse werden für jeden Versuch über den bestehenden echo-freien
Eingabekanal neu erfasst.
`--json` und sitzungsweites `--force` sind im Dialog unzulässig; Automation
verwendet weiterhin direkte Subcommands.

CLI und Backend geben technische Identität, Zustände, Phasen, Zähler und
geheimnisfreie Fehlercodes aus, aber keine privaten Schlüssel, internen
Systemausgaben oder ungefilterten Fehlertexte.
Die aufgabenorientierte Bedienung bleibt im
[Administrationshandbuch](https://github.com/lxndrp/lzug/wiki/Administration).

## OCI-Runtime und Infrastruktur

Das Produktimage `lzug-app` enthält das kompilierte Angular-Bundle, das aus dem
Backend-Wheel installierte Python-Backend, das portable CLI-Binary, die
Backend-Migrationen und produktive Python-Abhängigkeiten.
Tests, Demo-Seed, Dokumentation, Node.js/npm, uv und Lockfiles gelangen nicht
in das Runtime-Image.
Der Prozess läuft standardmäßig als UID/GID `10001:10001`, unterstützt ein
read-only Root-Dateisystem und verwendet nur `/data` dauerhaft sowie `/tmp`
flüchtig.

Docker Engine auf Linux ist die qualifizierte Referenz für Build, Release, CI
und Self-Hosting.
Das OCI-Image bleibt portabel; weitere konkrete Laufzeiten gehören nicht zum
unterstützten oder geprüften Umfang.
`deployment/self-hosted/compose.yaml` ist ein optionaler knapper Docker-Referenzweg für genau einen
`lzug-app`-Container und ein persistentes Volume.
Im Repository wird Compose vom Root mit explizitem Projektverzeichnis aufgerufen:

```sh
docker compose --project-directory . -f deployment/self-hosted/compose.yaml up -d
```

Damit bleiben lokale `.env`-Dateien und relative Host-Pfade am Repository-Root.
Eine separat heruntergeladene Compose-Datei verwendet weiterhin ihr eigenes
Installationsverzeichnis; der Standard für den Admin-Socket bleibt `./var/lzug-admin`.
Docker Compose validiert und startet den Referenzservice im Pester-Vertrag.
`tests/pester/Container.Tests.ps1` prüft den ausgelieferten Image- und
Compose-Vertrag: gemeinsame Build-Identität, tatsächliche Runtime-Rechte,
Frontend-Auslieferung, Health-Identität und die Verbindung der CLI zum
Backend-Socket.
Ein unterstützter Bootstrap-Roundtrip über Container-Neuerstellung prüft das
Volume-Mapping.
Fachliche HTTP- und Sicherheitsaussagen liegen in den Backend-Verträgen für
FastAPI-Abhängigkeiten, Security, HTTP-Parität, Ressourcenautorisierung und
OpenAPI.
Diagnostik, Einladung und Actorverhalten liegen in Backend-Admin-/Diagnostik-
und Go-CLI-Tests.
Backup, Export, Restore, Schlüsselgrenzen und Rollback liegen in
Backend-Backup-/Lifecycle-/Socket-Integration sowie CLI-Artefakt- und
Migrationsprüfungen.
`tests/pester/Operator.Tests.ps1` behält den echten PTY-Nachweis mit dem im Image
gebauten CLI-Binary.
`tests/pester/Compatibility.Tests.ps1` behält den historischen v0.6.0-Restore-
und Upgradevertrag samt bisheriger Ausführungsfrequenz.

`tests/pester/LzugHarness.ps1` bündelt native Aufrufe, isolierte Ressourcen,
Readiness und Cleanup.
Ein temporäres Compose-Override ersetzt ausschließlich das Socket-Bind-Mount
durch ein privates Engine-Volume, damit POSIX-Eigentum auch in Docker Desktop
geprüft werden kann.
Datenvolume, Servicebefehl, UID/GID, Read-only-Dateisystem und übrige
Sicherheitskonfiguration stammen aus `deployment/self-hosted/compose.yaml`.
Nur die kurzlebigen Vorbereitungsschritte erhalten die benötigten Root-Rechte;
Initialisierung und Service laufen als `10001:10001`.
Der Image-Smoke prüft effektive Eigentümer, Verzeichnis-Modus `0750` und
Socket-Modus `0660`.
Die Ablehnung unsicherer Socket-Verzeichnisse bleibt durch
`backend/tests/test_admin_socket.py` abgedeckt.

`tests/pester/Compatibility.Tests.ps1` startet die digestgebundene
v0.6.0-Fixture, erzeugt und restauriert ein Legacy-Backup und führt anschließend
die freigegebene Vorwärtsmigration über den Admin-Socket aus.
Der gemeinsame Image-Build erzeugt dafür zusätzlich eine ausschließlich lokale
Fixture mit synthetischen Release-Metadaten `v0.0.0-rc.0`;
Entwicklungsbuilds dürfen die Migration produktseitig nicht freigeben.
Dabei entstehen weder Git-Tag noch veröffentlichter Release.

Die öffentliche Demo verwendet das getrennte Image `lzug-demo` und ein
zugehöriges Seed-Image mit gemeinsamer Produktrevision, Runtimevertrag,
Schemafingerprint und Seed-Revision.
Die Verantwortungen innerhalb der Demo-Komponente sind an genau diesen Pfaden
festgelegt:

| Pfad | Verantwortung |
| --- | --- |
| `packaging/demo/contract.py` | kleinster gemeinsamer Identitäts-, Manifest- und Laufzeitvertrag ohne ausführbare Delivery-Werkzeuge |
| `packaging/demo/runtime/` | App-Einstieg, serverseitige Demo-Policy, Szenarioansicht, Arbeitskopien, Runtime-Verifikation und Seed-Initialisierung |
| `packaging/demo/artifacts.py` | Build-time Seed- und App-Manifeste; Veröffentlichung und Promotion bleiben bei Docker, GitHub Packages, Attestations und Azure CLI |
| `packaging/demo/Dockerfile` und `Dockerfile.seed` | Builddefinitionen für Demo-App und Seed-Artefakt bei unverändertem Root-Buildkontext |
| `deployment/demo/infra/` | vollständige OpenTofu-Topologie der öffentlichen Azure-Demo einschließlich unveränderter OIDC-, Environment- und State-Verträge mit `lzug-demo.tfstate` |
| `packaging/demo/tests/` | komponentenspezifische Runtime-, Delivery-, Container-, Infrastruktur- und Vertragsprüfungen der Demo |

Echte repositoryweite Integrations- und Lieferwegprüfungen bleiben unter
`tests/`.
Die Quellmodule liegen unter `packaging/demo/`, behalten zur Laufzeit aber
den Python-Namespace `demo`. Task und der Publication-Workflow ergänzen
`packaging` zu `PYTHONPATH`; so entsteht kein lokales Python-Paket `packaging`,
das die gleichnamige Tooling-Abhängigkeit verdecken könnte.
Runtime-Images kopieren nur `packaging/demo/contract.py` und die benötigten Module aus
`packaging/demo/runtime/`; der Build-time Artefaktbau aus `packaging/demo/artifacts.py` bleibt außerhalb
der laufenden Images.
Beim Einstieg erzeugt die Demo aus dem synthetischen Basisseed eine eigene
SQLite-Arbeitskopie pro Besuch.
Nur die drei Rollen dieses Besuchs teilen sie; Sitzung und Arbeitskopie laufen
ab Erzeugung nach höchstens 60 Minuten ab und werden bei Abmeldung oder Reset
verworfen.
Die Demo-Policy erlaubt ausschließlich die in ihrer Matrix gebundenen
Fachaktionen, unterdrückt externe Benachrichtigungszustellung und lässt die
produktive Autorisierung zusätzlich unverändert prüfen.
Das Datenvolume bleibt flüchtig und der tägliche Reset ist eine zusätzliche
Absicherung, kein Self-Hosting-Verfahren.
`deployment/demo/infra/` beschreibt die Azure-Ressourcen deklarativ; GitHub OIDC und das
geschützte Environment `demo` begrenzen echte Mutationen.

## Testeinstiege

| Änderung | Erster fokussierter Nachweis |
| --- | --- |
| Fachservice oder Repository | passendes Modul unter `backend/tests/` |
| HTTP-Assembly, Routerregistrierung oder OpenAPI-Vertrag | `backend.tests.test_fastapi_assembly`, `test_fastapi_app`, `test_openapi_contract` und betroffener API-Test |
| Demo-Runtime oder Demo-Artefakt | passendes Modul unter `packaging/demo/tests/` |
| Release-, SBOM- oder Workflowvertrag | passendes Modul unter `tests/delivery/` |
| Dokumentations- oder Publikationsvertrag | passendes Modul unter `tests/docs/` |
| Synthetische Fixture-Quelle | `backend/tests/test_synthetic_fixtures.py`, Backend- und Demo-Tests |
| Angular-Komponente oder Service | zugehöriger Vitest-Test unter `frontend/src/` |
| sichtbarer Hauptablauf | `task quality:e2e` und bei UI-Änderung `task quality:a11y` getrennt |
| Go-CLI | `cd operator-cli && go test ./...` beziehungsweise `task quality:operator` |
| OCI oder Compose | passendes Modul unter `tests/pester/` sowie `task quality:pester` |
| Repository-Tooling | passendes Modul unter `tests/tooling/` |
| Demo-Lieferung | `task quality:demo-deployment`, `task quality:demo` und bei Infrastruktur `task quality:infra` |

Die breite Auswahl und die lokalen Voraussetzungen stehen unter
[Entwicklung](development.md).
