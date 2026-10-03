# Frontend-Architekturvertrag

Dieser Vertrag beschreibt Zielverantwortung, Routen, Provider-Lebensdauern und
fachliche Datenflüsse des Angular-Frontends.
Die Entscheidung ist in [ADR-0042](decisions/0042-frontend-zustandsbesitz-und-feature-lebensdauern.md)
festgehalten.

## Frontend-Zielvertrag

[ADR-0042](decisions/0042-frontend-zustandsbesitz-und-feature-lebensdauern.md)
verbindet den bestehenden Angular-/REST-Vertrag aus ADR-0004 mit konkretem
Datenbesitz, Schreibrecht und Lebensdauer.
Die Matrix beschreibt das bestätigte Ziel.
Der folgende Ist-Hinweis hält befristete Übergangspfade fest, ohne sie als
Zielarchitektur auszugeben.

| Bereich | Daten- und Zustandsbesitz | Commands und Schreibrecht | Geteilte Referenzen und Konsumenten | Lebensdauer und Invalidierung |
| --- | --- | --- | --- | --- |
| Shell und Navigation | Shell besitzt Navigationszustand, globale Hinweise, Lifecycle-Anzeige und Zugriffssicht; keine Fachdaten oder fachlichen Workflow-Drafts. | Keine fachlichen Commands; Auth- und Session-Commands liegen beim Auth-Feature. | Auth-/Capability-Sicht für erlaubte Aktionen; globale Rückmeldungen nehmen Ergebnisse entgegen, besitzen aber nicht deren Fachdaten. | Shell bleibt während der App-Sitzung. Auth-/Sessionwechsel leert geschützte Ansichten; Navigation allein löscht keine anwendungsweiten Identitäts- oder Lifecycle-Werte. |
| Authentisierung und Session | Auth besitzt Anmeldung, Einladung/Aktivierung, Wiederherstellung, Sitzungsidentität und Auth-Antworten; auch eine ausstehende Server-Sitzungswiderrufung gehört hierher. | Anmelden, Einladung aktivieren, Zugang wiederherstellen, TOTP bestätigen und Sitzung beenden über `AuthService`/Auth-Feature. Demo-Rollenwechsel und Verlassen der Demo delegieren Sitzungseinrichtung beziehungsweise Abmeldung an Auth. | Authentisierte Identität und Berechtigungen sind begrenzte Referenzen für geschützte Features; die Shell konsumiert die Zugriffssicht. | Ansichtwechsel verwirft Einladungs-/Wiederherstellungstoken, Passwort-, TOTP- und angezeigte Wiederherstellungscode-Drafts sowie verspätete Antworten. Bei fehlgeschlagener Validierung hält Auth eine ausstehende Widerrufung persistent fest und bietet einen expliziten Wiederholungsbefehl; normale Initialisierung bleibt bis zum erfolgreichen Widerruf gesperrt. Erfolgreicher Sessionwechsel setzt den Kontext neu; geschützte Reads und Auswahlwerte der alten Sitzung werden invalidiert. |
| Auswahlkontext | `RoundContextService` besitzt die nullable ausgewählte Runden-ID; die ausgewählte Ausschuss-ID ist nur ein kleiner UI-Kontext. Keine Rundendaten, Boards oder Drafts. | Runde auswählen/wechseln; fachliche Änderung und Autorisierung verbleiben beim zuständigen Runden-Feature. Der Sessionkontext wird nach erfolgreicher Authentisierung explizit initialisiert. | IDs und wenige begründete Anzeigeinformationen für Routing und Commands; Feature-Reads bleiben Eigentum des jeweiligen Features. | Rundenwechsel verwirft alle rundenbezogenen Reads und Drafts. Jeder gestartete Command bindet die ursprüngliche Runden-ID; sein Ergebnis darf nicht in einen anderen Kontext geschrieben werden. Sessionwechsel löscht geschützte Auswahlwerte; ohne authentisierte Auswahl gibt es keine synthetische Standardrunde. |
| Dashboard | Eigene Übersicht, Summary und für die Dashboard-Aufgabe nötige Projektion. Keine Quelle für Orts-, Personal- oder Featurezustand. | Öffnen/Navigation zu Features; keine Mutationen fremder Fachbereiche. | Runde, kleine Zusammenfassungen und die für das Board angezeigten Orts-/Raumnamen als begrenzter Konsument; keine Voraussetzung für unabhängige Features. | Wechsel aus der Ansicht verwirft deren Reads/Projektion. Rundenauswahl, Sessionwechsel oder eine erfolgreiche Runden-Lifecycle-Mutation (Schließen, Abbrechen, Wiederöffnen oder Löschen), die seine Round-/Summary-Projektion ändert, invalidiert sie; betroffene Venue-/Raum-Umbenennungen invalidieren seine Orts-/Boardprojektion. Erneutes Öffnen lädt gezielt neu. |
| Prüfungsorte | Ortsfeature besitzt Venue-, Raum- und Kontaktdaten, Auswahl, Filter, Drafts, Lade-/Fehlerstatus und Geocoding-/Preflight-Ergebnisse. Reads sind ohne Runde verfügbar. | Orts-, Raum- und Kontaktänderungen, Geocoding, Dubletten-/Auswirkungsprüfungen, Promotionanträge/-entscheidungen und Folgeaufträge. Nur freigegebene Berechtigungen erlauben den jeweiligen Write. | Orts-IDs und schmale lesende Ortsreferenz für Planung, bestätigte Pläne und die Dashboard-Boardanzeige; diese Konsumenten besitzen keine Ortsmutation. | Ansichtswechsel verwirft Reads, Preflight und ansichtsgebundene Draft-Ergebnisse. Angenommene Venue-/Raum-/Kontaktänderungen bleiben an ihre Ursprungs-ID gebunden; verspätete Antworten aktualisieren keinen neuen Draft. Sessionwechsel invalidiert geschützte Ortsdaten. Erfolgreiche Commands übernehmen bestätigte Venue-/Raum-/Kontaktantworten oder invalidieren betroffene Orts-Reads; Änderungen angezeigter Venue-/Raumnamen invalidieren zusätzlich die Dashboard-Boardprojektion. |
| Stammdaten | Kandidaten und Ausschüsse besitzen ihre kanonischen Stammdaten im Master-Data-Feature; Listen, Editoren und Commands gehören zum jeweiligen Einstieg. | Kandidaten anlegen, ändern und löschen; Ausschussmitglieder anlegen und ihren Aktivstatus ändern. Diese Commands laufen über `MasterDataPort`. | Kandidaten, Ausschussmitglieder und Ausschüsse sind begrenzte Leseoptionen für Rundenwahl, Planung, bestätigte Pläne und Durchführung; Änderungen invalidieren gezielt die davon abhängigen Referenzen. | Ansichtswechsel verwirft lokale Such-/Edit-Drafts. Anlegen nutzt bis zur Antwort eine stabile Ansichts-/Operationskorrelation und wechselt danach zur Server-ID; andere Mutationen bleiben an die Ursprungsobjekt-ID gebunden. Sessionwechsel leert geschützte Daten. Rundenzuweisungen und von bestätigten Plänen angezeigte Kandidaten-/Mitgliedsoptionen werden bei relevanten Master-Data-Änderungen gezielt invalidiert (siehe Operationstabelle). |
| Prüfungshalbjahre und Rundenauswahl | Halbjahre und Runden-Lebenszyklus gehören dem Halbjahresfeature. Der ausgewählte Rundenzeiger gehört zum Auswahlkontext. Kandidatenzuordnungen werden hier nicht neu angelegt oder neu zugeordnet; terminale Statuscommands beenden eine aktive Zuordnung atomar mit der Änderung des RoundCandidate. | Runden anlegen, schließen, abbrechen, wieder öffnen, leere Runden löschen, terminale Kandidatenstatus setzen, IHK-Status dokumentieren und Lebenszyklusdaten exportieren. Die Auswahl löst nur einen Kontextwechsel aus. | Ausschüsse, Kandidaten und Zuordnungen sind begrenzte Stammdaten-Reads; Runden-ID wird an nachfolgende Commands übergeben. | Ansichtswechsel verwirft Feature-Reads/Drafts. Ein Rundenwechsel invalidiert alle abgeleiteten rundenbezogenen Views, nicht aber fachunabhängige Ortsdaten. Erfolgreiche Lifecycle-Mutationen invalidieren betroffene Dashboard- und Terminübersicht-Projektionen. Erfolgreiches Löschen der ausgewählten Runde leert die Auswahl nur, wenn sie noch auf die gelöschte Ursprungs-ID zeigt; danach ist eine explizite neue Auswahl erforderlich. Sessionwechsel löscht geschützte Listen. |
| Planung | Planung besitzt Rundenorganisation, Verfügbarkeiten, Tages-/Planungsentwürfe, Validierung und Vorschlagszustand. | Runden aktualisieren, Verfügbarkeiten anfordern/speichern, Prüfungstage anlegen/generieren/aktivieren/deaktivieren, Vorschläge erzeugen/speichern und erstmalig bestätigen werden durch Planning-Commands geschrieben. Vorschauerzeugung, Speichern eines bestehenden Vorschlags und Lesen des Vorschlags bleiben getrennte Vorgänge. Die Revision eines bereits bestätigten Plans gehört dem Feature Bestätigte Pläne und dessen `CONFIRMED_PLANS_PORT`. | Kandidaten-, Ausschuss-, Raum-/Orts-Referenzen werden nur als Read-Verträge konsumiert; Terminübersicht und bestätigte Pläne sind getrennte Konsumenten. | Ansichtswechsel verwirft Reads, Vorschlagsansichten, lokale Entwürfe und UI-Effekte des alten Einstiegs. Angenommene Commands bleiben an die Ursprungsrunde gebunden; Anlegen von Prüfungstagen nutzt bis zur Antwort eine Ansichts-/Operationskorrelation, Aktivieren/Deaktivieren behält die ursprüngliche Prüfungstag-ID. Nur ein Port, der eine Quellrevision annimmt, bindet den Write zusätzlich daran. Einstellungen, Verfügbarkeiten, Vorschauerzeugung und Erstbestätigung nehmen keine Quellrevision entgegen; beim Speichern eines bestehenden Vorschlags bleibt dessen angezeigte `revision` gebunden. Erfolgreiche Writes invalidieren gezielt geänderte Dashboard-/Terminübersicht-Projektionen; die erstmalige Planbestätigung invalidiert bestätigte Pläne. Antworten aktualisieren nur das Planning-Feature. Planrevisionsantworten folgen dem Ursprungskontext des Bestätigte-Pläne-Features und invalidieren betroffene Prüfungstag-Reads, damit diese die bestätigte Revision neu laden. Rundenwechsel setzt rundenbezogene Planung zurück. Sessionwechsel invalidiert geschützte Daten. |
| Bestätigte Pläne | Das Feature besitzt die Liste bestätigter Pläne, die Auswahl, Details, Revisionsentwurf und Revisionshistorie. | Bestätigte Pläne lesen sowie einen bestehenden bestätigten Plan mit Grund als neue Revision speichern; Queries und Revisionen laufen über `CONFIRMED_PLANS_PORT`. Die erstmalige Planbestätigung bleibt beim Planning-Feature. | Rundenauswahl und Plan-/Runden-IDs; Prüfungsorte und Stammdaten sind begrenzte Lese-Referenzen. Das Feature liefert die ausgewählte Plan-/Tag-Referenz an Prüfungstag. | Ansichtswechsel verwirft Listen-/Detail-Reads und lokale Revisionsentwürfe. Ein angenommener Revisions-Command bleibt an ursprüngliche Plan-/Runden-ID und Quellrevision gebunden. Rundenwechsel invalidiert die zugehörige Auswahl; eine erfolgreiche erstmalige Bestätigung oder Tagesmutation invalidiert betroffene Plan-/Tag-Projektionen. Sessionwechsel löscht geschützte Reads und Entwürfe. |
| Terminübersicht | Rundenübergreifende Übersicht der Prüfungstermine; sie besitzt keine Planungsschreibrechte. | Terminübersicht lesen; die ausgewählte Eintrags-ID dient der Navigation in Planung oder Bestätigte Pläne. Planungsänderungen gehören dem Planning-Feature. | Nur ausgewählte Eintrags-ID als Navigationskontext; sie konsumiert nicht den globalen Auswahlkontext und verändert weder Plan- noch Ortsdaten. Die Einträge enthalten Rundenname/-status und Kalenderwochen. | Ansichtswechsel verwirft den Overview-Read. Ein Wechsel der aktiven Runde wirkt sich nicht auf die rundenübergreifende Übersicht aus. Erfolgreiche Planning- oder Lifecycle-Writes invalidieren den Overview-Read, wenn sie dessen angezeigte Felder ändern. Sessionwechsel verwirft geschützte Reads. |
| Durchführung: Prüfungstag | Prüfungstag besitzt Tagesstatus, Anwesenheit, persönliche Anwesenheitserklärung und Tagesansicht. Die UI startet dort eigene oder koordinierte Ausfallmeldungen für eine Tageszuweisung; Command, Antwort und Datenbesitz bleiben im Personal-Feature. | Anwesenheit koordinieren, Slotstart/-status ändern, Prüfungstag schließen oder nach Auswirkungsprüfung wieder öffnen; Maschinen- und Textnachweis eines Tagesabschlusses auf ausdrückliche Anforderung exportieren; eigene Anwesenheit melden; eine eigene oder koordinierte Ausfallmeldung wird als Personal-Command an `PersonalFacade` delegiert. Die berechtigten Exportabfragen protokollieren einen Export, ändern aber nicht den fachlichen Abschlusszustand. | Runde und Tag sowie je nach Command Slot-ID oder Assignment-ID und die vom Command akzeptierte Tagesrevision verbinden Tages-Reads und Workflow-Commands. Kandidatenanwesenheit zielt auf einen Slot, Mitgliedsanwesenheit und koordinierte Ausfallmeldung auf eine Tageszuweisung. Abschluss-Exporte bleiben an die Ursprungs-Tag-ID gebunden. Personal stellt die Fähigkeit zur eigenen Ausfallmeldung oder autorisierten Koordination bereit, ohne den Personalzustand an Prüfungstag abzugeben. | Ansichtswechsel verwirft Tages-Reads und lokale Antworten. Tagescommands behalten die akzeptierten Ursprungs-IDs und Revisionen; die Personal-Ausfallmeldung bleibt an ihre Personal-Identität gebunden. Erfolgreiche Tagescommands aktualisieren die Day-eigene Revision und invalidieren betroffene Bestätigte-Plan-Projektionen. Bei einer Wiedereröffnung invalidieren betroffene Protokoll-/Ergebnisprojektionen, wenn die bestätigte Auswirkungsprüfung diese Entitäten umfasst. Ein ausdrücklich angeforderter Abschluss-Export bleibt an Tag und Sitzung gebunden; eine private Antwort wird nicht in eine andere Sitzung übernommen. Runden- und Sessionwechsel invalidieren geschützte Reads. |
| Durchführung: Protokoll | Protokollfeature besitzt Protokollinhalt, Revision, Änderungsentwurf, Abschluss-/Wiederöffnungszustand und Exportantworten. | Protokoll speichern, abschließen, wieder öffnen, Antworten erfassen, Korrektur anfordern/öffnen und exportieren; Konfliktbehandlung bleibt revisionsgebunden. | Runde und Tag sind geteilter Kontext. Ergebnis ist ein paralleler Konsument dieses Kontexts; es liest weder Protokoll-ID noch Protokollrevision über `ExamResultPort`. | Ansichtswechsel verwirft ungespeicherte, ansichtsgebundene Entwürfe und Reads. Mutationen binden die vom Port akzeptierten Protokoll-/Tagesrevisionen. Erfolgreiche Writes aktualisieren oder invalidieren die Day-eigene Tagesrevision und betroffene Bestätigte-Plan-Projektionen; die geteilte Revision wird den parallelen Protokoll-/Ergebnis-Konsumenten nach Refresh bereitgestellt. Export ist an Protokoll-ID und aktuellen Stand bei Anforderung gebunden; seine Antwort wird nur dem Ursprungsfeature zugestellt. Sessionwechsel invalidiert geschützte Inhalte. |
| Durchführung: Ergebnis | Ergebnisfeature besitzt Bewertung, Punkte, Teilnehmerergebnis, Revisionen und Exportzustand. | Bewertung speichern/zurücknehmen, Bewertungen offenlegen, Komponenten-/Gesamtergebnis feststellen und bestätigen, externes Ergebnis erfassen/bestätigen, Korrektur öffnen, Ergebnis mitteilen, Aufbewahrung setzen und vorhandene Exporte anfordern innerhalb der erteilten Fähigkeiten. | Runde und Tag sind geteilter Kontext mit dem Protokollfeature; die Slot-ID wählt das Ergebnis innerhalb des Tages aus. Dessen ID oder Revision ist keine Abhängigkeit des Ergebnisports. | Ansichtswechsel verwirft Read und lokalen Editor-Draft. Ein angenommener Write wird mit den vom Port akzeptierten Ursprungs-IDs und Revisionen fortgeführt. Erfolgreiche Writes aktualisieren oder invalidieren die Day-eigene Tagesrevision und betroffene Bestätigte-Plan-Projektionen; die geteilte Revision wird den parallelen Protokoll-/Ergebnis-Konsumenten nach Refresh bereitgestellt. Export wird nur an den Ursprungsworkflow zugestellt. Sessionwechsel löscht geschützte Ergebnisdaten. |
| Persönliche Funktionen | Persönlicher Bereich besitzt Benachrichtigungen, Zustellkanäle, Kalenderstatus/-ereignisse und Abwesenheitsmeldungen mit je lokaler Ansicht. | Benachrichtigungen und Kanäle lesen, Push-Endpunkt registrieren, Kalenderaktionen ausführen sowie Abwesenheit für die eigene Person oder ein zugewiesenes Ausschussmitglied melden und Vertretungsbefehle mit passender Fähigkeit. Eine eigene Ersatzantwort zielt auf die Response-ID; koordinierte Ersatzwahl zielt auf Abwesenheitsreport-ID, ausgewählte Ausschussmitglied-ID und Reportversion. | Authentisierte Identität und eigene Mitglieds-/Kalenderkennung; eine autorisierte Ausschusskoordination meldet Abwesenheit zu einer Tageszuweisung mit Tag-, Assignment-ID und akzeptierter Tagesrevision. Prüfungstag startet diese Aktion, übernimmt aber weder Report-Command noch Personalzustand. Die Ausschusskoordination bleibt im Personal-Feature. | Ansichtswechsel verwirft Ansichtsdaten und neue Reads; ein angenommener personenbezogener Command läuft in seinem Personal-Workflow fort. Erfolgreiche Abwesenheits-/Vertretungsbefehle invalidieren betroffene Day- und Bestätigte-Plan-Projektionen, wenn sie Tagesrevision, Besetzung oder Anwesenheit ändern. Eine neue Kalenderfeed-URL bleibt als einmaliges, derselben Sitzung zugeordnetes Ergebnis verfügbar, bis sie angezeigt/kopiert oder ausdrücklich verworfen wurde. Sessionwechsel löscht personenbezogene Reads und verhindert spätere Antwortübernahme in eine neue Sitzung. |
| Demo und Produktinformation | Demo besitzt Szenarioübersicht, Reset-Command und Tour-/Timerzustand; Demo-Rollenwechsel und Abmeldung sind Auth-Session-Commands. Produktinformation besitzt die Buildversion; demoabhängige Anzeige und Matrixversion stammen aus dem Auth-Sessionzustand. Fachänderungen innerhalb einer Demo-Szene bleiben beim jeweiligen Feature. | Demo-Reset ist ein expliziter Demo-Command; Rollenwechsel und Demo verlassen delegieren an `AuthService`. Tour und Navigation schreiben keine Fachaggregate. Ein bestätigter Reset/Rollenwechsel läuft zu Ende und erzeugt danach einen neuen Demo-Read. | Demo-Rolle und `demo_matrix_version` sind Auth-Sessionreferenzen; Produktinformation konsumiert die Buildversion. | Ansichtswechsel verwirft Szenario-Reads, lokale Auswahl und Tour-/Timerzustand. Der bestätigte Reset ist ein eigener bewusster Command, kein Effekt des Ansichtswechsels. Ein erfolgreicher Workspace-Reset bildet eine appweite Sessiongrenze: alle geschützten Reads, Drafts, Auswahlwerte und verspäteten Antworten werden invalidiert, bevor Demo-Reads neu beginnen. Rollen-/Sessionwechsel invalidiert geschützte Demo-Reads und lässt demoabhängige Produktinformation neu aus der Auth-Session ableiten. Produktversion bleibt an den App-Build gebunden. |

### Modulgrenzen

Die Module bezeichnen fachliche Zuständigkeiten und Feature-Assemblies; sie
schreiben keine Angular-`NgModule`-Klassen oder Verzeichnisstruktur vor.
Jedes Fachmodul besitzt seine Reads, Drafts und Commands.
Andere Module greifen ausschließlich über begrenzte Query-/Referenzverträge
und explizite IDs/Revisionen darauf zu.

```mermaid
flowchart TB
  Platform[Plattform: Shell / Navigation / Lifecycle]
  Auth[Authentisierung und Session]
  Selection[Auswahlkontext: aktive Runde]
  Dashboard[Dashboard]
  Overview[Terminübersicht]
  ConfirmedPlans[Bestätigte Pläne]
  Master[Stammdaten: Prüflinge / Ausschüsse]
  HalfYears[Prüfungshalbjahre und Rundenauswahl]
  Locations[Prüfungsorte]
  Planning[Planung]
  subgraph Execution["Durchführung — Featuregruppe, keine Modulabhängigkeit"]
    direction LR
    Day[Prüfungstag]
    Protocol[Protokoll]
    Result[Ergebnis]
  end
  Personal[Persönliche Funktionen]
  Demo[Demo]
  Product[Produktinformation]
  Router[Router / Feature-Assembly]
  Platform --> Router
  Router --> Auth
  Router --> Dashboard
  Router --> Overview
  Router --> ConfirmedPlans
  Router --> Day
  Router --> Master
  Router --> HalfYears
  Router --> Locations
  Router --> Planning
  Router --> Personal
  Router --> Demo
  Router --> Product
  Auth -. Identität / Fähigkeit .-> Personal
  Demo -->|Rollenwechsel / Abmelden| Auth
  Auth -. Session / Fähigkeit .-> Locations
  Auth -. Authentisierung / Sessionwechsel .-> Selection
  Selection -. Runden-ID .-> Planning
  Selection -. Runden-ID .-> HalfYears
  Master -. Kandidaten- / Ausschussreferenz .-> Planning
  Master -. Kandidaten- / Ausschussreferenz .-> ConfirmedPlans
  Locations -. angezeigte Venue- / Raumnamen .-> Dashboard
  Locations -. Orts- / Raumreferenz .-> Planning
  Planning -. erstmalige Planbestätigung .-> ConfirmedPlans
  ConfirmedPlans -. ausgewählte Plan-/Tagreferenz .-> Day
  Day -. Tag-/Slot-ID und Tagesrevision .-> Protocol
  Day -. Runden-/Tag-/Slot-ID .-> Result
```

Der Durchführungs-Cluster gruppiert Prüfungstag, Protokoll und Ergebnis; er
bezeichnet keine Abhängigkeit zu einem zusätzlichen `Execution`-Modul.
Die gestrichelten Kanten erlauben nur den benannten Read-/Referenzvertrag.
Sie übertragen weder Datenbesitz noch Schreibrecht an den Konsumenten.
Die Ansicht erfordert keine neue gemeinsame Fachdatenbibliothek.

### Route-to-Feature-Zuordnung

Jede Zeile benennt den tatsächlich konfigurierten URL-Pfad und den in
`app.routes.ts` geladenen Einstieg.
Bei gemeinsamem Einstieg sind die URLs einzeln aufgeführt; die Einordnung als
Gruppierung sagt nur, dass die aktuelle Routerkonfiguration dieselbe
Einstiegskomponente verwendet.
`/` leitet auf `/dashboard` und `/planning` auf `/scheduling-overview` um;
unbekannte Pfade leiten ebenfalls zum Dashboard um.
Diese Einträge laden keine eigene Route-Komponente.

| Route-Komponente oder direkter Einstieg | URL(s) | Feature-Komponente und fachlicher Besitzer |
| --- | --- | --- |
| `AuthFlowComponent` (gemeinsamer Einstieg für drei Auth-Aktionen) | `/login`, `/activate`, `/recover` | Auth-Feature: `AuthFlowComponent`; Authentisierung und Session liegen in `AuthService`. |
| `DashboardRouteComponent` | `/dashboard` | Dashboard: `DashboardComponent`; öffnet andere Features per Navigation. |
| `SchedulingOverviewRouteComponent` | `/scheduling-overview` | Terminübersicht: `SchedulingOverviewComponent`; Rundenwahl/Öffnen ist keine Planungsmutation. |
| `PlanningRouteComponent` | `/scheduling-overview/:roundId` | Planung: `PlanningComponent`; Route bindet die Runde und Befehle an `PlanningWorkflowService`. |
| `ConfirmedPlansRouteComponent` (gleicher Einstieg für Liste, Bearbeitung und Details) | `/confirmed-plans`, `/confirmed-plans/:roundId`, `/confirmed-plans/:roundId/edit` | Bestätigte Pläne: `ConfirmedPlansComponent`; die Gruppen teilen View, nicht einen neuen Featurebesitzer. |
| `ExamDayRouteComponent` | `/confirmed-plans/:roundId/days/:dayId` | Prüfungstag: `ExamDayComponent`; URL liefert Runde und Tag. |
| `CandidatesRouteComponent` | `/candidates` | Stammdaten Prüflinge: `CandidatesComponent`; Mutationen über `MasterDataWorkflowService`. |
| `CommitteeRouteComponent` | `/committee` | Stammdaten Ausschuss: `CommitteeComponent`; Mutationen über `MasterDataWorkflowService`. |
| `LocationsRouteComponent` (gleicher Einstieg für Liste/Detail) | `/locations`, `/locations/:id` | Prüfungsorte: `LocationsComponent`; `:id` ist eine selektierte Detailansicht desselben Features. |
| `ExamHalfYearsRouteComponent` | `/exam-half-years` | Prüfungshalbjahre/Rundenauswahl: `ExamHalfYearsComponent`. |
| Direkter Einstieg `NotificationsComponent` | `/notifications` | Persönliche Benachrichtigungen und Kalender: `NotificationsComponent` / Personal-Feature. |
| Direkter Einstieg `AbsenceReportsComponent` | `/absence-reports` | Persönliche Abwesenheiten: `AbsenceReportsComponent` / Personal-Feature. |
| Direkter Einstieg `DemoScenariosComponent` | `/demo-scenarios` | Demo-Szenarien: `DemoScenariosComponent`; Demo bleibt eigene Assembly/Sessionfunktion. |
| `AboutRouteComponent` | `/about` | Produktinformation: `AboutComponent`; App-Version aus Buildinformation, Demoindikator und Matrixversion aus der aktuellen Auth-Session. |

### Komponentenbaum

Die Featurekästen fassen Verantwortungen zusammen und schreiben keine
zusätzlichen Klassen vor.
Die Root-Shell rendert Routen über `router-outlet`; ein Route-Einstieg wird nur
dort gezeigt, wo `app.routes.ts` eine Bindungs- oder Kontextaufgabe hat.

```mermaid
flowchart TB
  App[App: Shell, Navigation, Zugriffssicht]
  Router[Angular Router / router-outlet]
  App --> Router
  Router --> Auth[Auth: Anmeldung / Aktivierung / Wiederherstellung]
  Router --> DashboardRoute[DashboardRouteComponent]
  DashboardRoute --> Dashboard[DashboardComponent]
  Router --> OverviewRoute[SchedulingOverviewRouteComponent]
  OverviewRoute --> Overview[SchedulingOverviewComponent]
  Router --> PlanningRoute[PlanningRouteComponent]
  PlanningRoute --> Planning[PlanningComponent]
  Router --> PlansRoute[ConfirmedPlansRouteComponent]
  PlansRoute --> Plans[ConfirmedPlansComponent]
  Router --> DayRoute[ExamDayRouteComponent]
  DayRoute --> Day[ExamDayComponent]
  Router --> CandidateRoute[CandidatesRouteComponent]
  CandidateRoute --> Candidates[CandidatesComponent]
  Router --> CommitteeRoute[CommitteeRouteComponent]
  CommitteeRoute --> Committee[CommitteeComponent]
  Router --> LocationsRoute[LocationsRouteComponent]
  LocationsRoute --> Locations[LocationsComponent]
  Router --> HalfYearsRoute[ExamHalfYearsRouteComponent]
  HalfYearsRoute --> HalfYears[ExamHalfYearsComponent]
  Router --> Notifications[NotificationsComponent]
  Router --> Absences[AbsenceReportsComponent]
  Router --> Demo[DemoScenariosComponent]
  Router --> AboutRoute[AboutRouteComponent]
  AboutRoute --> About[AboutComponent]
  Shared[Auth / Session / Lifecycle / Auswahlkontext]
  App --> Shared
```

### DI-Provider-Sicht (Ist-Komposition)

Diese Sicht entspricht der aktuellen `app.config.ts`-Root-Composition.
Ein gebundener Token zeigt die vorhandene Port-Adapter-Zuordnung;
`useExisting` teilt die vorhandene Auth- oder Lifecycle-Instanz.
Alle dort explizit gebundenen Ports/Adapter liegen im Root-EnvironmentInjector.
Services mit `providedIn: 'root'` — darunter aktuell Workspace- und
Workflow-Services — sind ebenfalls anwendungsweit erreichbare Singletons;
das Verlassen einer Route zerstört sie nicht.
Komponentenfelder und lokale Signals leben dagegen mit ihrer
Komponenteninstanz.
Diese Ist-DI-Lebensdauer ist nicht gleich fachlichem Datenbesitz.

Im Ziel bleiben Authentisierung, Session, Lifecycle und tatsächlich
zustandslose technische Adapter im Root-Injector.
Feature-Reads, Ansichtsselektion und Drafts erhalten eine View-/Route- oder
Feature-Injektorlebensdauer passend zur Matrix.
Nur ein Command, dessen Operationseintrag die Fortführung über den
Ansichtswechsel vorsieht, gehört einem Feature-Command-Eigentümer mit
festgehaltenem Ursprungskontext; ein Root-Provider ist dafür nicht automatisch
erforderlich.
Diese Dokumentation verschiebt noch keine Provider und behauptet keine
implementierte Feature-Injektorgrenze.

```mermaid
flowchart LR
  Root[app.config.ts / Root EnvironmentInjector]
  Root --> Router[provideRouter(routes)]
  Root --> Http[provideHttpClient / Interceptors]
  Root --> OverviewPort[SCHEDULING_OVERVIEW_PORT]
  OverviewPort --> OverviewAdapter[HttpSchedulingOverviewAdapter]
  Root --> PlanningPort[PLANNING_PORT]
  PlanningPort --> PlanningAdapter[HttpPlanningAdapter]
  Root --> HalfYearPort[EXAM_HALF_YEARS_PORT]
  HalfYearPort --> HalfYearAdapter[HttpExamHalfYearsAdapter]
  Root --> PersonalPort[PERSONAL_PORT]
  PersonalPort --> PersonalAdapter[HttpPersonalAdapter]
  Root --> ProtocolPort[EXAM_PROTOCOL_PORT]
  ProtocolPort --> ProtocolAdapter[HttpExamProtocolAdapter]
  Root --> ResultPort[EXAM_RESULT_PORT]
  ResultPort --> ResultAdapter[HttpExamResultAdapter]
  Root --> LocationPort[LOCATIONS_PORT]
  LocationPort --> LocationAdapter[HttpLocationsAdapter]
  Root --> LocationRead[LOCATIONS_READ_PORT]
  LocationRead --> LocationReadAdapter[HttpLocationsReadAdapter]
  Root --> MasterPort[MASTER_DATA_PORT]
  MasterPort --> MasterAdapter[HttpMasterDataAdapter]
  Root --> DayPort[EXAM_DAY_PORT]
  DayPort --> DayAdapter[HttpExamDayAdapter]
  Root --> WorkspacePort[WORKSPACE_PORT]
  WorkspacePort --> WorkspaceAdapter[HttpWorkspaceAdapter]
  Root --> PlansPort[CONFIRMED_PLANS_PORT]
  PlansPort --> PlansAdapter[HttpConfirmedPlansAdapter]
  Root --> DemoPort[DEMO_SCENARIOS_PORT]
  DemoPort --> DemoAdapter[HttpDemoScenariosAdapter]
  Root --> AuthPort[AUTHENTICATION_PORT useExisting]
  AuthPort --> Auth[AuthService]
  Root --> LifecyclePort[LIFECYCLE_AVAILABILITY_PORT useExisting]
  LifecyclePort --> Lifecycle[LifecycleService]
  Root --> ErrorPort[FRONTEND_ERROR_REPORTER_PORT]
  ErrorPort --> ErrorAdapter[HttpFrontendErrorReporter]
  Adapters[Weitere API-Clients und HttpClient]
  Http --> Adapters
  PlanningAdapter --> Adapters
  LocationAdapter --> Adapters
  WorkspaceAdapter --> Adapters
```

`LOCATIONS_READ_PORT` ist im aktuellen Code an `HttpLocationsReadAdapter`
gebunden, dessen Snapshot noch aus dem Workspace projiziert wird.
Das ist eine befristete Ist-Kopplung und wird mit dem Orts-Piloten #1067
entfernt.
Die globalen Workspace-Projektionen und ihre Verbraucher werden in den
Feature-Slices rückgebaut; die Root-Provider der Ports belegen keine
Workspace-Zuständigkeit.

### Datenfluss-Sicht

Die Pfeile zeigen fachliche Reads, Commands und gezielte Referenzen des
Zielvertrags, nicht einen zusätzlichen globalen Eventbus.
Durchgezogene Linien markieren Besitzer-/Command-Fluss; gestrichelte Linien
markieren begrenzte Leseverträge.

```mermaid
flowchart LR
  Shell[Shell / Navigation / Lifecycle]
  Auth[Auth / Session / Fähigkeiten]
  Context[Auswahlkontext: Runden-ID]
  Dashboard[Dashboard-Projektion]
  Locations[Orts-Reads und Orts-Commands]
  Master[Stammdaten-Reads und Commands]
  HalfYears[Halbjahre und Rundenauswahl]
  Planning[Planungs-Reads und Commands]
  ConfirmedPlans[Bestätigte Pläne: Auswahl / Revision]
  Overview[Terminübersicht]
  Day[Prüfungstag: Status / Anwesenheit]
  Protocol[Protokoll: Inhalt / Revision]
  Result[Ergebnis: Bewertung / Revision]
  Personal[Benachrichtigung / Kalender / Abwesenheit]
  Demo[Demo-Szenarien]
  API[Bestehende Backend-API und Autorisierung]
  Shell --> Auth
  Auth -->|Auth-Commands / Sessionwechsel| API
  Auth -. Identität / Fähigkeit .-> Context
  Auth -. Fähigkeit / Zielautorisierung .-> Day
  Auth -. Fähigkeit .-> Personal
  Context -. selected round ID .-> Dashboard
  Context -. selected round ID .-> HalfYears
  Context -. origin round ID .-> Planning
  Context -. round ID .-> ConfirmedPlans
  Dashboard -. Übersichtskonsum .-> API
  Locations -->|Venue Reads und eigene Commands| API
  Master -->|Stammdaten-Reads und eigene Commands| API
  HalfYears -->|Lifecycle-Commands| API
  Planning -->|Rundenbezogene Commands / erstmalige Planbestätigung| API
  ConfirmedPlans -->|Plan-Reads und Revisionen| API
  Overview -->|Termin-Reads| API
  Day -->|Tages-/Anwesenheitscommands und Abschluss-Exporte| API
  Protocol -->|Protokollrevision und Commands| API
  Result -->|Ergebnisrevision und Commands| API
  Personal -->|autorisierte Reads und Commands| API
  Demo -->|Demo-Fähigkeiten| API
  Master -. Kandidaten- und Ausschussreferenzen .-> HalfYears
  Master -. begrenzte Referenzen .-> Planning
  Master -. Kandidaten- und Ausschussreferenzen .-> ConfirmedPlans
  Locations -. angezeigte Venue- / Raumnamen .-> Dashboard
  Locations -. Orts-/Raumreferenzen .-> Planning
  Locations -. Orts-/Raumreferenzen .-> ConfirmedPlans
  Planning -. erstmalige Planbestätigung .-> ConfirmedPlans
  ConfirmedPlans -. ausgewählte Plan-/Tagreferenz .-> Day
  Overview -. ausgewählte Eintrags-ID zur Navigation .-> Planning
  Overview -. ausgewählte Eintrags-ID zur Navigation .-> ConfirmedPlans
  Day -. Tag-/Slot-ID und Tagesrevision .-> Protocol
  Day -. Runden-/Tagkontext .-> Result
  Day -. Slot-ID für die Ergebnisauswahl .-> Result
  Day -->|Abwesenheitsreport: Tag / Assignment / Revision| Personal
  Demo -->|Rollenwechsel / Abmelden| Auth
```

Jede geteilte Referenz hat einen Fachbesitzer und einen begrenzten
Konsumentenkreis.
Kandidaten- und Ausschussänderungen invalidieren nur Referenzprojektionen, die
diese Entitäten anzeigen oder für neue Commands benötigen.
Venue-/Raumänderungen invalidieren Ortsdaten und davon abhängige Planungs-,
Bestätigte-Plan- und Tagreferenzen, nicht die Runde als Ganzes.
Rundenänderungen invalidieren rundenbezogene Planung, Board, Tag, Protokoll
und Ergebnis; Ortsdaten bleiben gültig.
Protokoll- und Ergebnisänderungen verwenden bestätigte IDs/Revisionen und
invalidieren keine allgemeine Dashboardladung.
Sessionwechsel verwirft alle geschützten Feature-Reads unabhängig von diesen
gezielten fachlichen Regeln.

### Operations- und Invalidierungsvertrag

Die Ansichts-, Runden- und Sessionwechsel-Regeln gelten je Operationstyp wie
folgt.
`Verwerfen/abbrechen` bedeutet, dass ein Read, Ergebnis oder lokaler Draft
nicht in eine neue Ansicht übernommen wird.
`Weiterführen mit festgehaltenem Ursprung` gilt nur für bereits angenommene
Commands: Sie behalten den ursprünglichen Entitäts-, Runden-, Tag-, Identitäts- und
Revisionsbezug; eine Antwort wird nie in einen neu gewählten
Kontext geschrieben.
Mutierende Folgeaktionen, die eine Freigabe oder fachliche Vorschau erfordern,
werden `nur nach Bestätigung` angenommen.

| Bereich | Operation | Ansichtswechsel | Rundenwechsel | Sessionwechsel |
| --- | --- | --- | --- | --- |
| Shell und Navigation | Navigation, Lifecycle- und Zugriffssicht | Keine Fachdatenoperation; nur Ansichtszustand wechselt. | Shell bleibt; kontextbezogene Kennzeichnung wechselt. | Geschützte Navigation/Capabilities leeren und Auth-Sicht neu aufbauen. |
| Authentisierung und Session | Anmeldung, Einladung/Aktivierung, Wiederherstellung, TOTP bestätigen, Abmelden oder ausstehende Sitzungswiderrufung wiederholen | Auth-Einstiegswechsel verwirft Token-, Passwort-, TOTP- und angezeigte Wiederherstellungscode-Drafts; Antworten an den ursprünglichen Vorgang binden und nach Viewwechsel nicht in eine neue Auth-Ansicht übernehmen. Die Widerrufswiederholung ist eine explizite Auth-Operation im Shell-Recoveryzustand. | Kein Rundenkontext; Auth-Antworten ändern keine Runden-Reads. | Angenommene Auth-Commands behalten ihre Vorgangskorrelation. Bei fehlgeschlagener Sessionvalidierung hält Auth den ungeprüften Kontext gesperrt und persistiert den Widerrufungsbedarf; nur die erfolgreiche explizite Wiederholung löscht ihn und setzt den anonymen Zustand. Nach erfolgreichem Sessionwechsel alte geschützte Antworten, Drafts und Referenzen verwerfen; Session und Auswahl erst aus der neuen Auth-Antwort aufbauen. Rückbau der Auth-Response-Fencing- und Sensitive-Draft-Lebensdauer: #1097. |
| Auswahlkontext | Runden-ID auswählen/wechseln | Auswahl bleibt appweit, solange dieselbe Sitzung gilt. | Alte rundenbezogene Reads und Drafts `verwerfen`; neue Runde gezielt laden. Bereits angenommene Commands `weiterführen mit festgehaltenem Ursprung`. | Auswahl auf leer setzen; erst nach erfolgreicher Authentisierung aus einer expliziten Auswahl initialisieren. Die verantwortliche Transition vom heutigen `DEFAULT_ROUND_ID = 1` liegt im Auswahlkontext-Slice #1097. |
| Dashboard | Übersicht/Summary lesen | Read abbrechen und Projektion verwerfen; beim Wiederöffnen gezielt neu laden. | Alte Summary verwerfen; neue Runde/Übersicht laden. | Geschützten Read abbrechen und Ergebnis verwerfen. |
| Prüfungsorte | Orts-, Raum- und Kontaktlisten/Details lesen; Filter/Draft; Dubletten-, Geocoding- und Preflight-Ergebnis | Reads, Filter, Drafts und Prüfergebnisse abbrechen/verwerfen; kein unbestätigter mutierender Folgecommand. | Ortsread und Draft bleiben bestehen, da unabhängig von einer Runde. | Geschützte Reads, Filter, Drafts und Prüfergebnisse verwerfen. |
| Prüfungsorte | Venue/Raum/Kontakt anlegen, ändern oder löschen; Auswirkungsprüfung, Dublettenprüfung, Promotion und Folgecommand | Anlegen bis zur Antwort über stabile Ansichts-/Operationskorrelation verfolgen und erst danach die Server-ID verwenden; Update/Löschen bleiben an der Ursprungs-ID. Bestätigung gilt für Venue-Löschen, Dublettentreffer und Auswirkungen, wenn der konkrete Prüfpfad sie verlangt. Raum-/Kontaktanlage und -löschung sowie Kontaktänderungen und Promotionanträge/-entscheidungen werden nach expliziter Nutzeraktion direkt ausgeführt; Raumänderungen bestätigen nur relevante Auswirkungen. Andere ausdrücklich vorschaupflichtige Zweige behalten ihre Bestätigung. | Kein Rundenkontext; angenommener Ortscommand läuft weiter. Betroffene Bestätigte-Plan- und Tag-Reads mit Venue-/Raumprojektionen gezielt invalidieren; eine Änderung angezeigter Venue-/Raumnamen invalidiert zusätzlich das Dashboard-Board. Terminübersicht nicht invalidieren, wenn sie keine Ortsreferenz enthält. | Vor Annahme verwerfen; bereits angenommene Commands behalten ihre Ursprungsidentität. Antwort darf weder Draft noch Daten einer neuen Sitzung aktualisieren. |
| Stammdaten | Kandidaten-/Ausschusslisten und Details lesen; Such-/Edit-Draft | Read abbrechen, lokalen Such-/Edit-Draft verwerfen; neu öffnen lädt gezielt. | Fachunabhängige Stammdaten-Reads bleiben; rundenbezogene Zuordnungsprojektionen invalidieren. | Geschützte Reads und Drafts verwerfen. |
| Stammdaten | Kandidat anlegen/ändern/löschen; Ausschussmitglied anlegen oder Aktivstatus ändern | Anlegen bis zur Antwort über stabile Ansichts-/Operationskorrelation verfolgen und erst danach die Server-ID verwenden; andere Mutationen bleiben an der Ursprungsobjekt-ID. Nur der bestätigte Datensatz wird aktualisiert. Bei Erstellung, Änderung oder Löschung die jeweils betroffenen Runden-IDs mit dem Command festhalten; Neuzuordnung hält Quell- und Zielrunde. | Angenommener Stammdatencommand bleibt an sein Objekt gebunden. Kandidatenerstellung invalidiert die Zuordnungsprojektionen ihrer Zielrunde; Kandidatenlöschung invalidiert Zuordnungsprojektionen jeder betroffenen Runde; Neuzuordnung invalidiert sie in Quell- und Zielrunde. Für alle betroffenen Runden Dashboard-/Planungsprojektionen aktualisieren; bei geänderten angezeigten Referenzen zusätzlich Kandidaten-/Mitgliedsoptionen bestätigter Pläne invalidieren. | Vor Annahme abbrechen; danach Command im Ursprungsobjekt fortführen, Antwort nicht in neue Sitzung übernehmen. |
| Prüfungshalbjahre/Rundenauswahl | Halbjahr- und Rundendaten lesen; Lifecycle-Daten anzeigen | Read abbrechen, lokale Auswahl-/Filterzustände verwerfen. | Alte rundenbezogene Reads verwerfen; neue Zielrunde gezielt laden. | Geschützte Reads/Drafts verwerfen. |
| Prüfungshalbjahre/Rundenauswahl | Runde anlegen, schließen, abbrechen, wieder öffnen oder leere Runde löschen; terminalen Kandidatenstatus setzen; IHK-Status dokumentieren | Explizit gestartete Lifecycle-Commands an ursprünglicher Halbjahres-/Runden-ID fortführen; wo der Port eine Revision verlangt, die Ursprungsrevision binden. Rundenanlage bis zur Antwort über Ansichts-/Operationskorrelation verfolgen und erst danach die Server-ID verwenden. Terminale Statusänderungen, die die Kandidatenzuordnung beenden, samt Abschlussrevision in derselben atomaren Lifecycle-Operation fortführen; dies ist von einer Master-Data-Neuzuordnung getrennt. | Angenommener Command bleibt bei der Quellrunde; sein Ergebnis darf die neu ausgewählte Runde nicht ändern. Terminalstatus `transferred`, `postponed` oder `ihk_terminated` deaktiviert den RoundCandidate und beendet eine aktive Ausschusszuordnung innerhalb derselben Transaktion; die Quellrunden-Projektionen werden invalidiert. Eine erfolgreiche Lifecycle-Mutation invalidiert die Dashboard-Round-/Summary- und Terminübersicht-Projektion, falls diese von der geänderten oder gelöschten Runde abhängt. Nach erfolgreichem Abbrechen werden betroffene Bestätigte-Pläne-, Prüfungstag- und persönliche Kalenderprojektionen invalidiert, weil Tage, Slots und zukünftige Kalenderereignisse der Runde storniert werden. Erfolgreiches Löschen leert die Auswahl nur dann, wenn sie noch auf die gelöschte Ursprungs-ID zeigt; danach wird keine Ersatzrunde automatisch gewählt. | Vor Annahme verwerfen; danach nur im Ursprungsworkflow fortführen und geschützte Antwort verwerfen. |
| Prüfungshalbjahre/Rundenauswahl | Lifecycle-Export anfordern | Export nur auf expliziten Exportbefehl; an die Runden-ID der angeklickten Tabellenzeile binden, nicht an die globale Rundenauswahl. | Export gehört zur Ursprungsrunde und darf keine neu ausgewählte Runde aktualisieren. | Vor Annahme abbrechen; danach private Antwort nicht in eine neue Sitzung übernehmen. |
| Planung | Rundenplan, Verfügbarkeiten, Prüfungszeiten, Validierung und gespeicherten Vorschlag lesen | Read abbrechen und Ansichtszustand verwerfen; erneut öffnen lädt gezielt. | Alte Reads, Validierung und Vorschlag verwerfen. | Geschützte Reads abbrechen und verwerfen. |
| Planung | Vorschlag erzeugen | Als expliziten Write an die bei Aufruf gewählte Ursprungsrunde und den ursprünglichen Feature-Workflow binden. Die Erzeugungsoperation nimmt keine Quellrevision entgegen. | Angenommener Write bleibt bei der Quellrunde; veralteten Vorschlagszustand verwerfen und gezielt neu laden. | Vor Annahme abbrechen; danach in Ursprungsrunde und -sitzung fortführen, geschützte Antwort nicht in neue Sitzung übernehmen. |
| Planung | Bestehenden Vorschlag speichern | Als expliziten Write an die Ursprungsrunde und den ursprünglichen Feature-Workflow binden; die `revision` des geladenen `EditablePlanningProposal` für die optimistische Sperre erhalten. | Angenommener Write bleibt bei der Quellrunde; nach Erfolg aktualisiert nur die bestätigte Serverantwort den Vorschlag. | Vor Annahme abbrechen; danach in Ursprungsrunde und -sitzung fortführen, geschützte Antwort nicht in neue Sitzung übernehmen. |
| Planung | Runde aktualisieren, Verfügbarkeiten anfordern, Prüfungstag anlegen/generieren/aktivieren/deaktivieren | Explizite Writes an die Ursprungsrunden-ID binden. Prüfungstag-Anlage bleibt bis zur Serverantwort an Ansichts-/Operationskorrelation gebunden; Statusänderungen behalten die ursprüngliche Prüfungstag-ID. Bei Ansichtswechsel wird die Antwort nur dem Ursprungsworkflow zugestellt. | Angenommener Write läuft in seiner Ursprungsrunde fort; keinen anderen Auswahlkontext aktualisieren. | Vor Annahme abbrechen; danach nur im Ursprungsworkflow fortführen und geschützte Antworten verwerfen. Erfolgreiche Writes invalidieren geänderte Dashboard-/Terminübersicht-Felder; die erstmalige Bestätigung invalidiert die bestätigte-Pläne-Projektion. |
| Planung | Einstellungen/Verfügbarkeiten speichern; Vorschlag bestätigen (erstmalige Planbestätigung) | Speichern nach explizitem Command; erstmalige Bestätigung nur nach fachlicher Bestätigung. Danach mit festgehaltener Runden-ID fortführen. Nur wenn der konkrete Port eine Quellrevision annimmt, diese ebenfalls binden; die aktuellen Einstellungen-, Verfügbarkeits- und Bestätigungsports nehmen keine Quellrevision entgegen. Antwort betrifft nur diesen Plan. | Angenommener Command bleibt an Quellrunde gebunden; darf neuen Kontext nicht aktualisieren. | Vor Annahme abbrechen; danach in Quellrunde fortführen, Antwort nicht in neue Sitzung übernehmen. |
| Bestätigte Pläne | Liste, Details, Planrevisionen und Revisionshistorie lesen; Revisionsentwurf bearbeiten | Read abbrechen und lokalen Revisionsentwurf verwerfen. | Auswahl- und Readzustand für die alte Runde verwerfen; neu öffnen lädt deren bestätigten Plan gezielt. Plan-/Tagauswahl bleibt Featurekontext und wird nur als explizite Referenz an Prüfungstag übergeben. | Geschützte Reads und Revisionsentwürfe verwerfen. |
| Bestätigte Pläne | Bestehenden bestätigten Plan mit Änderungsgrund als neue Revision speichern | Nach explizitem Nutzercommand annehmen und mit ursprünglicher Plan-/Runden-ID und Quellrevision fortführen; nur bestätigte Revision aktualisiert den Ursprungsplan. | Angenommener Revisionscommand bleibt am Ursprungsplan und aktualisiert keine neu gewählte Runde. | Vor Annahme abbrechen; danach im Ursprungsworkflow fortführen, Antwort nicht in eine neue Sitzung übernehmen. |
| Terminübersicht | Rundenübergreifende Termine lesen; Eintrag zur Navigation auswählen | Beim Verlassen der View den Read abbrechen; die Eintrags-ID dient nur der Navigation. | Kein Effekt auf den rundenübergreifenden Overview-Read. | Geschützte Reads verwerfen. |
| Prüfungstag | Tagesstatus, Anwesenheit und Fehlmeldung lesen; lokale Antwort | Read abbrechen; lokale Antwort verwerfen. | Tagesread und Draft zur alten Runde/am alten Tag verwerfen. | Geschützte Tagesdaten und Antwort verwerfen. |
| Prüfungstag | Maschinen- oder Textnachweis des Tagesabschlusses exportieren | Nur auf ausdrückliche Exportaktion und mit der Ursprungs-Tag-ID anfordern; erfolgreiche Abfrage erzeugt den Export-Auditdatensatz, ändert aber nicht den fachlichen Tagesabschluss. | Export gehört zur Ursprungs-Tag-ID; keine Übernahme einer privaten Antwort in einen anderen Tag. | Vor Annahme abbrechen; nach Annahme die Exportantwort nur in der Ursprungssitzung zustellen, nicht in eine neue Sitzung übernehmen. |
| Prüfungstag | Kandidatenanwesenheit auf Slot setzen; Mitgliedsanwesenheit auf Tageszuweisung setzen; eigene An-/Abwesenheit melden | Erst nach explizitem Nutzercommand annehmen; danach mit ursprünglicher Runde, Tag-ID, tatsächlicher Slot- oder Assignment-ID und akzeptierter Tagesrevision weiterführen. | Angenommener Tagescommand bleibt am Ursprungstag; keine Übernahme in den neuen Tag. Erfolgreicher Write aktualisiert die Day-eigene Revision und invalidiert betroffene Bestätigte-Plan-Projektionen. | Vor Annahme abbrechen; danach Ursprungscommand fortführen, Antwort darf keine Daten der neuen Sitzung verändern. |
| Prüfungstag | Slot starten/Status ändern, Tag schließen; Wiedereröffnung voranzeigen und ausführen | Read/Preview abbrechen und verwerfen. Angenommene Commands an die vom Port akzeptierte Tages-/Slot-ID und Tagesrevision binden. | Command und Ergebnis bleiben an Ursprungsrunde und -tag gebunden; keine Übernahme in neue Auswahl. Erfolgreicher Write aktualisiert die Day-eigene Revision und invalidiert betroffene Bestätigte-Plan-Projektionen. Bei Wiedereröffnung mit Protokoll-/Ergebnisbezug werden die in der bestätigten Auswirkungsprüfung genannten Protokoll-/Ergebnis-Reads invalidiert. | Vor Annahme abbrechen; danach nur im Ursprungsworkflow fortführen und geschützte Antwort verwerfen. |
| Protokoll | Protokoll/Revision lesen, lokalen Änderungsentwurf erstellen | Read abbrechen, ungespeicherten Draft verwerfen. | Read/Draft zur alten Runde, Tag- und Protokollrevision verwerfen. | Geschützten Read/Draft verwerfen. |
| Protokoll | Speichern, abschließen, wieder öffnen, antworten, Korrektur anfordern/öffnen; Export anfordern | Mutation nur als expliziter Command; Export nur nach explizitem Exportbefehl. Mutationen an den vom Port akzeptierten Protokoll-/Tagesrevisionen binden; konkurrierende Antwort überschreibt keinen neueren Read. Export verwendet Protokoll-ID und aktuellen Stand bei Anforderung; Antwort nur an Ursprungsworkflow zustellen. | Operation an ursprünglicher Tag-/Protokollrevision fortführen; Export/Antwort nicht in neue Runde übernehmen. Erfolgreiche Mutationen aktualisieren oder invalidieren die Day-eigene Tagesrevision und betroffene Bestätigte-Plan-Projektionen; Protokoll- und Ergebnis-Child-Reads werden aus dem erneuerten Day-Kontext geladen. | Vor Annahme abbrechen; danach im Ursprungsworkflow fortführen, private Antwort nicht in neue Sitzung übernehmen. |
| Ergebnis | Ergebnis/Revision und bereitgestellte Exportreferenzen lesen; Bewertungsentwurf bearbeiten | Read abbrechen und lokalen Editor-Draft verwerfen; Exportreferenzen nur zum angezeigten Ursprungsergebnis verwenden. | Read/Draft zur alten Runde, Tag- und Ergebnisrevision verwerfen. | Geschützten Read/Draft verwerfen. |
| Ergebnis | Bewertung speichern/zurücknehmen, offenlegen, Komponente/Gesamtergebnis feststellen und bestätigen, externes Ergebnis erfassen/bestätigen, Korrektur öffnen, Ergebnis mitteilen und Aufbewahrung setzen | Nur nach explizitem Nutzercommand annehmen. Commands binden die vom Port akzeptierten Ergebnis-/Tagesrevisionen; bestätigte Antworten aktualisieren nur das Ursprungsergebnis. | Am Ursprungsergebnis und den akzeptierten Tagrevisionen fortführen; keine Aktualisierung der neu gewählten Runde. Erfolgreiche Mutationen aktualisieren oder invalidieren die Day-eigene Tagesrevision und betroffene Bestätigte-Plan-Projektionen; Protokoll- und Ergebnis-Child-Reads werden aus dem erneuerten Day-Kontext geladen. | Vor Annahme abbrechen; danach Ursprungscommand fortführen, geschützte Antwort nicht in neue Sitzung übernehmen. |
| Ergebnis | Maschinen- oder Textnachweis für ein vorhandenes Ergebnis exportieren | Export nur nach ausdrücklichem Nutzerbefehl; als dauerhafte/auditierte Operation behandeln, nicht als abbrechbaren Read. Exportanforderung an die Ursprungs-Ergebnis-ID und die aktuelle Sitzung binden. | Serverseitige Export-Auditierung bleibt erhalten; eine private Exportantwort wird ausschließlich im Ursprungsergebnis und derselben Sitzung ausgeliefert. | Vor Annahme abbrechen; danach die Operation am Ursprungsergebnis fortführen und die private Antwort nicht in eine neue Sitzung übernehmen. |
| Persönliche Funktionen | Benachrichtigungen, Kalender und Abwesenheitsmeldungen gemäß Ausschussberechtigung lesen; Ansichtsfilter/Draft | Read abbrechen, View-Zustand verwerfen; beim Wiederöffnen gezielt neu laden. | Personenbezogene Reads bleiben bei Rundenauswahl gültig; nur explizite Rundenreferenzen neu laden. | Personenbezogene Reads, Filter und Drafts löschen. |
| Persönliche Funktionen | Push-Endpunkt registrieren, Kalenderfeed aktivieren/rotieren/widerrufen, Kalenderereignis laden oder herunterladen, Abwesenheit für sich oder ein zugewiesenes Ausschussmitglied melden, eigene Ersatzantwort geben; Ausschusskoordination wählt Ersatz | Aktion nur nach explizitem Nutzercommand annehmen; danach mit ursprünglicher Identität weiterführen. Eine koordinierte Abwesenheitsmeldung bindet Tag-ID, Assignment-ID und akzeptierte Tagesrevision. Eigene Ersatzantwort bindet Response-ID; koordinierte Ersatzwahl bindet Report-ID, Ziel-Ausschussmitglied-ID und Reportversion. Die bei Aktivierung/Rotation einmalig ausgegebene Kalenderfeed-URL bleibt im selben Sessionkontext angezeigt/kopierbar, bis sie bestätigt oder ausdrücklich verworfen wurde. | Angenommene persönliche Aktion läuft unabhängig von der Rundenauswahl. Erfolgreiche Abwesenheits-/Vertretungswrites invalidieren betroffene Day- und Bestätigte-Plan-Projektionen, wenn Tagesrevision, Besetzung oder Anwesenheit betroffen sind. | Vor Annahme abbrechen; angenommener Command bleibt in Ursprungsidentität, seine Antwort darf die neue Sitzung nicht verändern. One-time feed result nicht vor Anzeige/Bestätigung verwerfen. |
| Demo | Szenarien lesen, Szenario auswählen, Tour/Timer bedienen | Read abbrechen; lokale Auswahl sowie Tour-/Timerzustand verwerfen. | Keine Rundendatenabhängigkeit; Demo-Rollen-/Sessionzustand bleibt separat. | Geschützten Read verwerfen; Tour-/Timer- und Rollenansicht zurücksetzen. |
| Demo/Auth | Demo-Reset, Rollenwechsel oder Demo verlassen | Szenario-/Reset-Operationen über Demo-Fähigkeiten direkt ausführen. Rollenwechsel und Verlassen als explizite Auth-Commands über `AuthService.startDemoSession()` beziehungsweise `AuthService.logout()` abwickeln; neue Sitzung und Capabilities nur nach erfolgreicher Auth-Sessionantwort übernehmen. | Kein impliziter Reset oder Rollenwechsel durch Rundenauswahl. | Demo-Reset ist eine appweite Workspace-/Sessiongrenze: alle geschützten Reads, Drafts, Auswahlwerte und verspäteten Antworten invalidieren, bevor geschützte Features oder Demo neu laden. Rollenwechsel/Abmelden löscht ebenfalls geschützte Alt-Reads; alter Command darf keinen Zustand der neuen Sitzung überschreiben. |
| Produktinformation | Buildversion sowie demoabhängige Anzeige/Matrixversion lesen | Buildversion bleibt unverändert; Demoindikator und Matrixversion beim Viewwechsel aus aktueller Auth-Session ableiten. | Buildversion bleibt unverändert; keine Rundendatenabhängigkeit. | Nur die Buildversion ist buildgebunden. Demoindikator und Matrixversion werden bei Sessionwechsel invalidiert und aus der neuen Auth-Session berechnet. |

Diese Matrix ist der konkrete Fortführungsvertrag für die Befehle in der
Verantwortungsmatrix; ihre Operationseinträge bestimmen die jeweilige
Abbruch-, Bestätigungs- und Fortführungsregel.
Ein bestätigter Command ist keine Zusage, den alten Bildschirm oder seine
Drafts wiederherzustellen; nach Abschluss wird dessen Antwort nur dem
Ursprungsfeature zugestellt.
Sessionwechsel verwirft geschützte Ansichten auch dann, wenn ein angenommener
Command im Ursprungsworkflow noch abgeschlossen wird.

### Übergangsverträge und Rückbau

| Bestehender Pfad | Befristeter Besitzer | Ziel und zuständiger Rückbau |
| --- | --- | --- |
| `ApplicationWorkspaceService` bündelt Runde, Summary, Board und Stammdaten; mehrere Ansichten lesen daraus. | Aktuell globaler Workspace; nicht Zielbesitzer der jeweiligen Fachdaten. | Ortsprojektion und Ortsladezustand entfernen: #1067. Dashboard-/Stammdatenzustand trennen: #1092. |
| Planung liest Runde, Summary, Board und Stammdaten aus dem Workspace. | `PlanningWorkflowService` besitzt bereits Planungscommands und lokale Proposal-/Editorzustände; Workspace bleibt nur Kompatibilitätsleser. | Eigenständige Planung-Reads und Ursprungskontext; Workspace-Abhängigkeit entfernen: #1093. |
| Prüfungstag, Protokoll und Ergebnis verwenden eigene Featureports, aber Teile des Shell-/Workspacekontexts und bestehende mehrstufige Ketten. | Jeweilige Featurekomponente und vorhandene Application/Facade/Port; IDs/Revisionen bleiben explizit. | Prüfungstagszustand verantworten: #1094; Protokoll-/Ergebniszustand und Grenzen bereinigen: #1095. |
| Persönliche Ansichten und Ansichten für Halbjahre, bestätigte Pläne, Produktinformation konsumieren teils geteilte Workspacewerte oder breite Einstiege. | Das jeweilige Feature bleibt fachlicher Besitzer; Workspace ist Kompatibilität. | Personal lokal und mit gezielten Fähigkeiten: #1096; Auth-Response-Fencing und sensible Draft-Lebensdauer sowie verbleibende Einstiege und Workspace-/Session-Übergänge: #1097. |
| Route-Einstiege und fachliche Services existieren parallel. | Route besitzt URL-Bindung/Command-Origin, Feature besitzt Fachzustand. | Beibehalten, solange beide eine dieser Aufgaben tragen; #1097 entfernt nur reine Durchreichung. |

Jede Rückbauänderung erhält vorhandene Lade-, Fehler-, Berechtigungs-,
Revisions-, Session- und Accessibility-Semantik.
Es wird weder ein Universal-Workspace noch eine Pflichtschicht je Request
eingeführt.
