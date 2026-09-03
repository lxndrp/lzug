# Komponenten

Die Anwendung bleibt ein modularer Monolith mit vier klaren technischen
Verantwortungsbereichen: Backend, Frontend, lokale Betreiber-CLI und
Auslieferungsinfrastruktur.
Gemeinsame Verträge werden an den Grenzen genutzt, nicht in mehreren
Komponenten nachimplementiert.

## Verantwortungen und Abhängigkeiten

| Bereich | Verantwortung | Zulässige Außengrenze | Maßgebliche Quellen |
| --- | --- | --- | --- |
| Backend | HTTP, Authentifizierung, Fachservices, Persistenz, Dokumente und Integrationsadapter | OpenAPI/JSON, Admin-JSON, SQLite und kontrollierte Provideradapter | `backend/`, `db/` |
| Frontend | aufgabenorientierte Ausschussoberfläche, Routing, Formulare und sichtbare Zustände | same-origin API über zentrale Modelle und Services | `frontend/src/app/` |
| Betreiber-CLI | lokale portable Orchestrierung von Administration, Diagnose und Lifecycle | einzelne Docker-/Podman-`exec`-Argumente und Admin-Protokollversion 1 | `cmd/lzug-admin/`, `.goreleaser.yml` |
| OCI und Self-Hosting | gemeinsames Produktimage, gehärtete Laufzeit und persistentes `/data` | `Dockerfile`, `compose.yaml` und Containerverträge | Dockerfiles, Compose und `scripts/*container*` |
| Öffentliche Demo | flüchtige App-/Seed-Assembly, Reset, Promotion und Azure-Deployment | digestgebundene Manifeste, OIDC und Demo-Runtime-Policy | `demo/`, `Dockerfile.demo*`, `infra/demo/`, Demo-Workflows |

Das Frontend greift nicht direkt auf Persistenz zu.
Die Go-CLI kennt weder Datenbankpfad noch SQL und enthält keine Fach-,
Migrations-, Backup-, Restore- oder Kryptologik.
Demo-Policy und Deploymentautomation dürfen Produktregeln nur einschränken oder
synthetische Erweiterungen aktivieren, aber keinen zweiten Produktkern bilden.

## Backend

`backend.fastapi_app.create_app` ist die produktive HTTP-Assembly.
`backend.server` startet sie über Uvicorn; `backend.transport` bildet den
gemeinsamen Transportvertrag ab.
Session, CSRF, Actor, Ausschuss-Scope und Fehlerübersetzung liegen am
HTTP-Rand, während der synchrone Anwendungskern frameworkunabhängig bleibt.

| Schicht | Verantwortung und Erweiterungspunkt |
| --- | --- |
| HTTP und Sicherheit | FastAPI-Routen, Request-/Responsemodelle, Session, CSRF, Autorisierung, Upload- und Konfigurationsgrenzen; keine Fachentscheidung im Handler |
| Anwendung | `backend.application` und fachliche Services; Use Cases, Invarianten und Transaktionsgrenzen ohne Webframework |
| Planung und Durchführung | Planung, Verfügbarkeit, Ausfall/Ersatz, Protokolle, Ergebnisse, Tages- und Rundenlebenszyklus |
| Integrationen | Benachrichtigung, persönliche Kalender und Dokumentablage; externe Zustellung bleibt best effort |
| Persistenz | Modelle, Repositories, Store und Datenbank; Schema und Migrationen sind ausführbare Quellen |
| Betrieb | Runtime-Policy, Observability, Build-Metadaten, Adminservice, Artefakte und Lifecycle |

Neue Fachregeln beginnen in einem Service und seinen fokussierten Tests.
Repositories kapseln fachnahe Persistenzzugriffe; Adapter übersetzen HTTP,
Dateien, Kalender oder Zustellkanäle.
Eine neue Speicher- oder Transporttechnik darf die Invarianten weder kopieren
noch umgehen.

Die [Python-Referenz](reference/backend.md) wird aus den öffentlichen
Google-Style-Docstrings erzeugt.
OpenAPI entsteht direkt aus der FastAPI-Assembly.
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
API-Modelle und der zentrale API-Service bilden die Backendgrenze;
fachliche Komponenten halten keine parallele Transport- oder
Autorisierungslogik.

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
Eingabe, Renderer sowie Docker-/Podman-Transport ohne IoC-Framework,
Service Locator, Reflection oder versteckte Registrierung.

Der Transport validiert den expliziten Containernamen und ruft den
Python-Adminprozess ohne Shell-Stringverkettung auf.
Kleine Aufträge und Antworten sind genau ein UTF-8-JSON-Objekt;
Artefaktoperationen trennen den potenziell großen Binärstrom von der
strukturierten Kontrollantwort.
Command-Handler greifen weder direkt auf Persistenz zu noch kennen sie
Engine-spezifische Details; Docker und Podman verwenden denselben versionierten
Backendauftrag.

Die Befehlsgruppen umfassen:

- lokale, geheimnisfreie Diagnose mit `status`, `config` und `doctor`;
- Konto- und Ausschussverwaltung ohne fachliches Leserecht;
- Benachrichtigungs- und Planfolgenverarbeitung;
- geschützte Backups, nicht mutierende Prüfung, vollständigen Restore und
  geschützten Vollexport;
- releasegebundenes Upgrade und nicht mutierende Rollback-Freigabe in einem
  ausdrücklich vorbereiteten Wartungscontainer.

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
Nur Engine und Containername dürfen mit der Priorität Flag,
Umgebungsvariable, optionale JSON-Datei und Standardwert konfiguriert werden.
`lzug-admin config inspect` zeigt diese effektiven Werte und ihre Herkunft,
ohne Konfiguration zu verändern.

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
Engine-Ausgaben oder ungefilterten Fehlertexte.
Die aufgabenorientierte Bedienung bleibt im
[Administrationshandbuch](../portal/betreiben.md).

## OCI-Runtime und Infrastruktur

Das Produktimage enthält das kompilierte Angular-Bundle, Python-Backend,
Migrationen und produktive Python-Abhängigkeiten.
Tests, Demo-Seed, Dokumentation, Node.js/npm, uv und Lockfiles gelangen nicht
in das Runtime-Image.
Der Prozess läuft standardmäßig als UID/GID `10001:10001`, unterstützt ein
read-only Root-Dateisystem und verwendet nur `/data` dauerhaft sowie `/tmp`
flüchtig.

`compose.yaml` ist die Self-Hosting-Referenz für genau einen Produktcontainer
und ein persistentes Volume.
Standardtooling prüft die Compose-Struktur; die kleine lzug-Policy prüft nur
projektspezifische Invarianten wie unveränderliche Images und den
Runtimevertrag.
Container-, Compose- und CLI-zu-Container-Smokes teilen Engine-Auswahl,
Lifecycle, Health-Waiting und Build-Identitätsprüfung in
`scripts/container-contract.sh`.

Die öffentliche Demo verwendet ein separates Produkt-/Seed-Imagepaar mit
gemeinsamer Produktrevision, Runtimevertrag, Schemafingerprint und
Seed-Revision.
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
`infra/demo/` beschreibt die Azure-Ressourcen deklarativ; GitHub OIDC und das
geschützte Environment `demo` begrenzen echte Mutationen.

## Testeinstiege

| Änderung | Erster fokussierter Nachweis |
| --- | --- |
| Fachservice oder Repository | passendes Modul unter `backend/tests/` |
| HTTP- oder OpenAPI-Vertrag | `backend.tests.test_fastapi_app`, `test_openapi_contract` und betroffener API-Test |
| Angular-Komponente oder Service | zugehöriger Vitest-Test unter `frontend/src/` |
| sichtbarer Hauptablauf | `task quality:e2e` und bei UI-Änderung `task quality:a11y` getrennt |
| Go-CLI | `go test ./cmd/lzug-admin` beziehungsweise `task quality:operator` |
| OCI oder Compose | `task quality:container`, `task quality:compose` oder `task quality:operator-container` |
| Demo-Vertrag | `task quality:demo-deployment`, `task quality:demo` und bei Infrastruktur `task quality:infra` |

Die breite Auswahl und die lokalen Voraussetzungen stehen unter
[Entwicklung](development.md).
