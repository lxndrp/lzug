# Komponenten

Die Anwendung bleibt ein modularer Monolith mit vier klaren technischen
Verantwortungsbereichen: Backend, Frontend, lokale Betreiber-CLI und
Auslieferungsinfrastruktur.
Gemeinsame Verträge werden an den Grenzen genutzt, nicht in mehreren
Komponenten nachimplementiert.
Die gemeinsame AIO-, Admintransport- und Lifecyclegrenze legt
[ADR-0033](decisions/0033-aio-betrieb-admintransport-und-lifecycle.md) fest.

## Verantwortungen und Abhängigkeiten

| Bereich | Verantwortung | Zulässige Außengrenze | Maßgebliche Quellen |
| --- | --- | --- | --- |
| Backend | ein autoritativer Prozess für HTTP, Admin-Socket, Lifecycle, Fachservices, Persistenz, Dokumente und Integrationsadapter | OpenAPI/JSON, versionierter Unix-Socket-Vertrag, SQLite und kontrollierte Provideradapter | `backend/src/backend/`, `backend/db/` |
| Frontend | aufgabenorientierte Ausschussoberfläche, Routing, Formulare und sichtbare Zustände | same-origin API über zentrale Modelle und Services | `frontend/src/app/` |
| Betreiber-CLI | portable Orchestrierung von Administration, Diagnose und Lifecycle | direkter Unix-Socket oder System-OpenSSH-Forwarding desselben Adminvertrags | `operator-cli/cmd/lzug-admin/`, `operator-cli/internal/admincli/`, `operator-cli/internal/tools/cli-reference/`, `operator-cli/.goreleaser.yml` |
| OCI und Self-Hosting | Produktimage `lzug-app`, gehärtete Docker-Referenz und persistentes `/data` | `Dockerfile`, optionaler Docker-Compose-Weg und Containerverträge | Dockerfile, Compose und `scripts/*container*` |
| Öffentliche Demo | getrenntes Image `lzug-demo`, flüchtige App-/Seed-Assembly, Reset, Promotion und Azure-Deployment | digestgebundene Manifeste, OIDC und Demo-Runtime-Policy | `demo/contract.py`, `demo/runtime/`, `demo/delivery/`, `demo/containers/`, `demo/infra/`, `demo/tests/`, Demo-Workflows |

Das Frontend greift nicht direkt auf Persistenz zu.
Die Go-CLI kennt weder Datenbankpfad noch SQL und enthält keine Fach-,
Migrations-, Backup- oder Restorelogik.
Die age-Hülle bleibt ihre einzige kryptographische Verantwortung; private
Schlüssel verlassen den Bedienrechner nicht.
Demo-Policy und Deploymentautomation dürfen Produktregeln nur einschränken oder
synthetische Erweiterungen aktivieren, aber keinen zweiten Produktkern bilden.

## Eigentümermatrix der Root-Konfiguration

Die Matrix hält die Entscheidung für den Root-Bestand fest.
Ein Pfad bleibt nur dann am Root, wenn er mehrere Komponenten versorgt,
als kanonischer Standard-Einstieg erwartet wird oder den unveränderten
Buildkontext voraussetzt.

| Datei | Eigentümer | Entscheidung und Begründung |
| --- | --- | --- |
| `.mise.toml` | Repository | Am Root behalten: ein gemeinsamer Toolchain-Pin für Python, Node.js, Go, Hugo, Lychee, uv, Task, Syft, GoReleaser und OpenTofu. |
| `Taskfile.yml` | Repository | Am Root behalten: kanonischer Einstieg für Setup, Tests, Dokumentation, Qualität, SBOM und Entwicklung. |
| `pyproject.toml` | Python-/Dokumentations-Toolchain | Am Root behalten: Backend, Demo, Skripte, Tests und MkDocs teilen ein uv-Projekt und einen Tooling-Vertrag. |
| `uv.lock` | Python-/Dokumentations-Toolchain | Am Root behalten: einziger Lockfile für das gemeinsame uv-Projekt; kein zweites Python-Toolingprojekt. |
| `.python-version` | Python-/Dokumentations-Toolchain | Am Root behalten: alle Python-Verbraucher verwenden dieselbe Version. |
| `.node-version` | Frontend | Nach `frontend/.node-version` verschoben: die Versionsdatei gehört ausschließlich zum npm-/Angular-Verbraucher. |
| `mkdocs.yml` | Dokumentation | Nach `docs/mkdocs.yml` verschoben: MkDocs-Konfiguration und Dokumentationsquellen liegen zusammen. |
| `.env.example` | OCI-/Self-Hosting | Am Root behalten: Beispielkonfiguration und kanonischer Einstieg direkt neben `compose.yaml`. |
| `Dockerfile` | OCI-/Self-Hosting | Am Root behalten: standardgebundener Produkt-Build für den unveränderten Root-Kontext. |
| `Dockerfile.demo` | Öffentliche Demo | Unter `demo/containers/Dockerfile.demo`: ausschließlich Demo-App-Assembly; der Root bleibt Buildkontext. |
| `Dockerfile.demo-seed` | Öffentliche Demo | Unter `demo/containers/Dockerfile.demo-seed`: ausschließlich Demo-Seed-Assembly; der Root bleibt Buildkontext. |
| `compose.yaml` | OCI-/Self-Hosting | Am Root behalten: kanonischer Compose-Einstieg für die dokumentierte Installation. |
| `.dockerignore` | OCI-/Self-Hosting | Am Root behalten: technisch an den unveränderten Root-Buildkontext gebunden. |
| `.github/` | Repository | Am Root behalten: GitHub erwartet Workflows, Vorlagen und Dependabot-Konfiguration dort. |
| Community-, Lizenz- und Support-Dateien | Repository | Am Root behalten: GitHub- und Community-Standards sowie rechtliche Hinweise erwarten diese Einstiege dort. |

## Backend

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
`backend.fastapi_http` stellt ihnen und der zentralen Transportgrenze die
gemeinsame Response-, Attachment- und Same-Origin-Abbildung bereit.
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
`resource_ownership` löst Ausschuss- und Rundenbesitz im übergebenen Store auf,
ohne eine weitere Session zu öffnen.
`resource_visibility` begrenzt Listen und Einzelabfragen bereits in SQL;
historische Rundenzuordnungen und aktive Kandidatenzuständigkeit behalten ihre
unterschiedlichen Sichtbarkeitsregeln.
Zusammengehörige Autorisierungs- und Sichtbarkeitsabfragen verwenden über
`read_session_scope` einen expliziten SQLite-Lese-Snapshot.
Die Ausführung eines Fachbefehls bleibt eine eigene Servicetransaktion.
Session, CSRF, Actor, Ausschuss-Scope und Fehlerübersetzung liegen am
HTTP-Rand, während der synchrone Anwendungskern frameworkunabhängig bleibt.
`backend.fastapi_dependencies` stellt dafür gemeinsame FastAPI-Dependencies
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
`backend.admin` kapselt bis zur vollständigen Socketumstellung den bisherigen
stdin/stdout-Einstieg als Kompatibilitätsadapter.

Die folgende Tabelle ist die kanonische knappe Zuordnung der aktuellen
Backend-Paketstruktur.
Abhängigkeiten verlaufen nur in die genannten Zielpakete; der automatisierte
Architekturtest verhindert nicht zugeordnete Module, unerlaubte Richtungen und
Zyklen zwischen den acht Kernpaketen.

| Paket | Verantwortung | Darf abhängen von |
| --- | --- | --- |
| `application/` | frameworkneutrale Use-Case-Orchestrierung, Ressourcenfassade, Transportobjekte und HATEOAS | `assessment`, `execution`, `identity`, `integrations`, `operations`, `persistence`, `planning` |
| `planning/` | Planaggregate, mögliche Prüfungstage, Prüfungsorte und Folgen bestätigter Änderungen | `integrations`, `persistence` |
| `execution/` | Ausfall und Ersatz, Protokolle, Tagesabschluss und Rundenlebenszyklus | `identity`, `integrations`, `persistence` |
| `assessment/` | individuelle Bewertungen und festgestellte Ergebnisse | `execution`, `identity`, `persistence` |
| `identity/` | Authentisierung, Autorisierung, Mitgliedschaften und lokale Betreiberidentität | `persistence` |
| `integrations/` | Kalender, Benachrichtigungen, Dokumentablage, Feiertage und Kartenanbieter | `identity`, `persistence` |
| `persistence/` | Modelle, Datenbank, Migrationen und niedrige Store-Primitive | keine anderen Kernpakete |
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

Das Angular-Frontend verwendet TypeScript, Angular Router und Taiga UI.
Es ist ein ruhiges Arbeitswerkzeug für wiederkehrende Ausschussprozesse und
keine Marketingoberfläche.
Fachliche API-Modelle und API-Clients unter `frontend/src/app/api/` bilden die
Backendgrenze.
`ApiClient` besitzt den gemeinsamen HTTP- und Collection-Transport;
Planung, Stammdaten, Prüfungsrunden, bestätigte Pläne, Prüfungstage,
Prüfungsprotokolle, Ergebnisse, persönliche Daten und Prüfungsorte besitzen
jeweils einen fachlichen Client.
Der schmale `api.models.ts`-Export hält bestehende Importpfade stabil, ohne
Transportmodelle erneut zu definieren.
Fachliche Komponenten halten keine parallele Transport- oder
Autorisierungslogik.

`ApplicationWorkspaceService` hält ausschließlich den fachübergreifenden
Lesezustand des gewählten Prüfungskontexts.
Planungs-, Stammdaten- und Ortsbefehle liegen in den zuständigen
Workflow-Services; `App` bleibt für Authentisierung, Navigation,
Zugriffsansicht und die Anbindung der Feature-Ereignisse verantwortlich.

`RoundContextService` hält den aktuellen Prüfungsrundenkontext.
Dashboard, Stammdaten, Planung, Durchführung und Nachweise bleiben fachlich
erkennbare Bereiche.
Der Entwicklungsproxy leitet `/api` an das lokale Backend weiter; produktiv
werden Browser-Bundle und API same-origin aus dem OCI-Image bereitgestellt.

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
Eine statische Registry ordnet jeden Command nach dem Muster
`lzug-admin <objekt> <aktion>` ein und ist die gemeinsame Quelle für Parser,
Hilfe, Completion und die
[generierte Befehlsreferenz](reference/cli.md).
Explizite Konstruktorverdrahtung verbindet Registry, Konfiguration, sichere
Eingabe, Renderer sowie direkten Unix-Socket- und System-OpenSSH-Transport ohne
IoC-Framework,
Service Locator, Reflection oder versteckte Registrierung.

Der lokale Transport verbindet sich direkt mit dem gehärteten Unix-Domain-Socket.
Der entfernte Transport übergibt strukturierte Argumente an System-OpenSSH und
leitet denselben Socketvertrag weiter, ohne Shell-Stringverkettung,
abgeschwächte Hostprüfung oder SSH-Agent-Weiterleitung.
Kleine Aufträge und Antworten sind genau ein UTF-8-JSON-Objekt;
Artefaktoperationen trennen den potenziell großen Binärstrom von der
strukturierten Kontrollantwort.
Command-Handler greifen weder direkt auf Persistenz zu noch kennen sie
Container-Engine-spezifische Details; direkter und SSH-weitergeleiteter Zugriff
verwenden denselben versionierten Backendauftrag.
Ein im `lzug-app`-Container gestartetes CLI-Binary verwendet ebenfalls direkt
den Socket.

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
Nicht geheime Zielprofile wählen direkten Socket oder System-OpenSSH und dürfen
Hostalias, entfernten Socketpfad und lokale Weiterleitungsart referenzieren.
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
SSH-Ausgaben oder ungefilterten Fehlertexte.
Die aufgabenorientierte Bedienung bleibt im
[Administrationshandbuch](../portal/betreiben.md).

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
`compose.yaml` ist ein optionaler knapper Docker-Referenzweg für genau einen
`lzug-app`-Container und ein persistentes Volume.
Standardtooling prüft die Compose-Struktur; die kleine lzug-Policy prüft nur
projektspezifische Invarianten wie unveränderliche Images und den
Runtimevertrag.
Container-, Compose- und CLI-zu-Container-Smokes teilen Docker-Lifecycle,
Health-Waiting und Build-Identitätsprüfung in
`scripts/container-contract.sh`.

Die öffentliche Demo verwendet das getrennte Image `lzug-demo` und ein
zugehöriges Seed-Image mit gemeinsamer Produktrevision, Runtimevertrag,
Schemafingerprint und Seed-Revision.
Die Verantwortungen innerhalb der Demo-Komponente sind an genau diesen Pfaden
festgelegt:

| Pfad | Verantwortung |
| --- | --- |
| `demo/contract.py` | kleinster gemeinsamer Identitäts-, Manifest- und Laufzeitvertrag ohne ausführbare Delivery-Werkzeuge |
| `demo/runtime/` | App-Einstieg, serverseitige Demo-Policy, Szenarioansicht, Arbeitskopien, Runtime-Verifikation und Seed-Initialisierung |
| `demo/delivery/` | Artefaktbau, Veröffentlichungsprüfung und Kommandozeilenadapter des gemeinsamen Vertrags |
| `demo/containers/` | Builddefinitionen für Demo-App und Seed-Artefakt bei unverändertem Root-Buildkontext |
| `demo/infra/` | vollständige OpenTofu-Topologie der öffentlichen Azure-Demo einschließlich unveränderter OIDC-, Environment- und State-Verträge mit `lzug-demo.tfstate` |
| `demo/tests/` | komponentenspezifische Runtime-, Delivery-, Container-, Infrastruktur- und Vertragsprüfungen der Demo |

Echte repositoryweite Integrations- und Lieferwegprüfungen bleiben unter
`tests/`.
Runtime-Images kopieren nur `demo/contract.py` und die benötigten Module aus
`demo/runtime/`; Build- und Veröffentlichungswerkzeuge aus `demo/delivery/`
bleiben außerhalb der laufenden Images.
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
`demo/infra/` beschreibt die Azure-Ressourcen deklarativ; GitHub OIDC und das
geschützte Environment `demo` begrenzen echte Mutationen.

## Testeinstiege

| Änderung | Erster fokussierter Nachweis |
| --- | --- |
| Fachservice oder Repository | passendes Modul unter `backend/tests/` |
| HTTP-Assembly, Routerregistrierung oder OpenAPI-Vertrag | `backend.tests.test_fastapi_assembly`, `test_fastapi_app`, `test_openapi_contract` und betroffener API-Test |
| Demo-Runtime oder Demo-Artefakt | passendes Modul unter `demo/tests/` |
| Release-, SBOM- oder Workflowvertrag | passendes Modul unter `tests/delivery/` |
| Dokumentations- oder Publikationsvertrag | passendes Modul unter `tests/docs/` |
| Synthetische Fixture-Quelle | passendes Modul unter `tests/fixtures/` und `task fixtures:check` |
| Angular-Komponente oder Service | zugehöriger Vitest-Test unter `frontend/src/` |
| sichtbarer Hauptablauf | `task quality:e2e` und bei UI-Änderung `task quality:a11y` getrennt |
| Go-CLI | `cd operator-cli && go test ./...` beziehungsweise `task quality:operator` |
| OCI oder Compose | passendes Modul unter `tests/oci/` sowie `task quality:container`, `quality:compose` oder `quality:operator-container` |
| Repository-Tooling | passendes Modul unter `tests/tooling/` |
| Demo-Lieferung | `task quality:demo-deployment`, `task quality:demo` und bei Infrastruktur `task quality:infra` |

Die breite Auswahl und die lokalen Voraussetzungen stehen unter
[Entwicklung](development.md).
