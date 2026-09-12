# Architektur und Entscheidungen

`lzug` ist ein modularer Monolith für die Arbeit eines Prüfungsausschusses.
Die Übersicht verwendet die für das Projekt hilfreichen arc42-Blickrichtungen
und C4-Abstraktionen, ohne eine vollständige Schablone oder eine zweite
technische Referenz zu pflegen.
Code, Schema, Migrationen, OpenAPI, Containerverträge und Workflows bleiben für
ihre Details maßgeblich.

## Systemkontext

```mermaid
flowchart LR
  member["Person: Ausschussmitglied<br/>plant und führt Prüfungen durch"]
  operator["Person: Betreiber:in<br/>pflegt Instanz und Konten lokal"]
  lzug["Software System: lzug<br/>unterstützt Planung, Durchführung und Nachweise<br/>für genau einen Ausschuss je Instanz"]
  push["Externes Software System: Push-Dienst<br/>optionale technische Zustellung"]
  smtp["Externes Software System: SMTP-Relay<br/>optionaler E-Mail-Fallback"]

  member -->|"HTTPS im Browser"| lzug
  operator -->|"lokale Betreiberbefehle"| lzug
  lzug -.->|"datenminimierte Zustellung"| push
  lzug -.->|"optionale E-Mail"| smtp
```

Fachliche Arbeit ist auf aktive Mitgliedschaften der lokalen Instanz begrenzt.
Betreiberzugriffe bleiben lokal und verleihen keine fachlichen Rechte.
Push und SMTP sind optionale technische Kanäle; ihr Ausfall entfernt weder
interne Hinweise noch einen bereits bestätigten Fachzustand.
Eine zentrale IHK-Plattform und ein externer Identitätsprovider gehören nicht
zum aktuellen System.

## Container-Sicht

Im C4-Sinn bezeichnet ein Container eine laufende Anwendung oder einen
Datenspeicher, nicht nur einen OCI-Container.
Die kanonische Prozess-, Transport- und Lifecyclegrenze steht in
[ADR-0033](decisions/0033-aio-betrieb-admintransport-und-lifecycle.md).

```mermaid
flowchart LR
  member["Person: Ausschussmitglied"]
  operator["Person: Betreiber:in<br/>lokal oder via System-OpenSSH"]
  channels["Externe Systeme:<br/>Push-Dienst und SMTP-Relay"]

  subgraph system["Software System: lzug"]
    spa["Container: Angular SPA<br/>Browser-Oberfläche"]
    app["Container: autoritativer Backendprozess<br/>HTTP- und Unix-Socket-Adapter,<br/>Anwendungskern und Lifecycle"]
    admin["Container: lzug-admin<br/>portable Go-CLI"]
    data[("Container: SQLite und /data<br/>Fachdaten, Dokumente<br/>und Backups")]
  end

  member -->|"bedient"| spa
  spa -->|"same-origin JSON/HTTPS"| app
  operator -->|"direkter oder SSH-weitergeleiteter CLI-Aufruf"| admin
  admin -->|"versionierter Auftrag über Unix-Domain-Socket"| app
  app -->|"SQLAlchemy und Dateizugriff"| data
  app -.->|"best effort"| channels
```

Browser-Bundle, Python-Anwendung und CLI werden gemeinsam im OCI-Image
`lzug-app` ausgeliefert, bleiben aber getrennte C4-Container mit expliziten
Transportgrenzen.
Genau ein Backendprozess führt die Persistenz und bedient HTTP sowie den
lokalen Admin-Socket als Adapter desselben Anwendungskerns.
`lzug-admin` erreicht lokal oder über System-OpenSSH denselben Socketvertrag;
ein Netzwerk-Adminendpunkt und ein zweiter Adminprozess existieren nicht.

## Komponenten-Sicht

```mermaid
flowchart LR
  spa["Angular-Komponenten<br/>Routing, Formulare, Zustände"]
  client["API-Service und Modelle<br/>OpenAPI-Grenze"]
  cli["Go-CLI<br/>Registry, Renderer und Transportwahl"]

  subgraph process["Ein autoritativer Backendprozess"]
    http["FastAPI-Adapter<br/>Session, CSRF und Fach-Scope"]
    socket["Unix-Socket-Adapter<br/>Betreiberautorisierung und Adminvertrag"]
    lifecycle["Lifecyclekoordination<br/>Live, Ready, Wartung und Migration"]
    core["Anwendungsservices<br/>Fachlogik und Transaktionen"]
    repo["Repositories und Integrationsadapter<br/>Persistenz, Dokumente, Kalender, Zustellung"]
  end

  store[("SQLAlchemy, SQLite und /data")]

  spa --> client
  client --> http
  http --> core
  http --> lifecycle
  cli -->|"direkt oder via System-OpenSSH"| socket
  socket --> core
  socket --> lifecycle
  core --> repo
  lifecycle --> repo
  repo --> store
  cli -->|"age-Hülle; private Identität bleibt lokal"| artifact["Geschütztes Artefakt"]
```

Die statische Go-Registry trennt Command-Metadaten, Validierung,
Backendauftrag, Transport und Darstellung und wird in einer sichtbaren
Composition Root explizit verdrahtet.
Transport- und Adapterdetails dürfen keine Fachlogik duplizieren.
Services und Repositories bleiben frameworkunabhängig; HTTP- und
Unix-Socket-Adapter verwenden im selben Prozess dieselben fachlichen und
betrieblichen Kernverträge.
Betreiberautorisierung am Socket und fachliche Webautorisierung bleiben
getrennt; keine der beiden Grenzen ersetzt die andere.
Die Verantwortungen und Testeinstiege sind unter
[Komponenten](components.md) zusammengefasst.

## Deployment-Sicht

```mermaid
flowchart TB
  member["Person: Ausschussmitglied"]
  local["Person: lokale Betreiber:in"]
  remote["Person: entfernte Betreiber:in<br/>mit lzug-admin"]

  subgraph host["Deployment Node: Self-Hosting-Host"]
    tls["Deployment Node: betreiberseitiger TLS-Endpunkt<br/>nicht Teil des Images"]
    ssh["Executable: System-OpenSSH<br/>Authentisierung und Socket-Forwarding"]
    admin["Executable: lzug-admin<br/>direkter Socketzugriff"]

    subgraph engine["Deployment Node: Docker auf Linux"]
      subgraph image["Container-Instanz: lzug-app<br/>UID/GID 10001, read-only Root-Dateisystem"]
        app["Prozess: autoritatives Backend<br/>HTTP, Anwendungskern und Lifecycle"]
        socket["Unix-Domain-Socket<br/>lokaler Adminadapter"]
        container_cli["Executable: lzug-admin<br/>bei Bedarf kurzlebig gestartet"]
      end
      data[("Volume: /data<br/>SQLite, Dokumente,<br/>Schlüssel und Backups")]
    end
  end

  member -->|"HTTPS"| tls
  tls -->|"HTTP an Port 8000"| app
  local -->|"lokaler Aufruf"| admin
  remote -->|"System-SSH"| ssh
  admin -->|"direkt"| socket
  ssh -->|"Socket-Forwarding"| socket
  container_cli -->|"direkt"| socket
  socket --> app
  app -->|"einziger dauerhafter Schreibbereich"| data
```

Der direkte Einstieg `lzug-admin <objekt> <aktion>` und der geführte Einstieg
`lzug-admin cli` enden in derselben statischen Registry und demselben
Ausführungspfad.
Der Dialog ergänzt ausschließlich Navigation, Eingabe, Zusammenfassung und
Statusrückmeldung.
Er enthält weder eigene Commandparameter noch Backendaufträge oder
Fachlogik.
Lokaler Zugriff, ein im Container gestartetes CLI-Binary und
SSH-Socket-Forwarding verändern weder Bedien- noch Commandvertrag.
Die Containerplattform startet Image, Container und bei Bedarf die CLI; sie ist
nicht der fachliche Backendtransport.

Die unterstützte Referenz ist eine einzelne Self-Hosting-Instanz mit
`lzug-app`, Docker auf Linux und persistenter `/data`-Grenze.
Compose ist ein optionaler knapper Docker-Referenzweg für genau diesen einen
Service.
Die OCI-Liefergrenze bleibt portabel; weitere konkrete Laufzeiten gehören
dadurch nicht zum unterstützten oder geprüften Umfang.
TLS-Terminierung, Host-Härtung, Schlüsselverwahrung, Sicherung und
Aufbewahrung liegen in Betreiberverantwortung und sind im
[Betreiberanleitung](https://github.com/lxndrp/lzug/wiki/Administration) beschrieben.
Die öffentliche Demo verwendet das getrennte Image `lzug-demo`, eine flüchtige
Azure-Assembly mit synthetischem Basisseed und kein Self-Hosting-Muster.
Ihre Runtime-Policy erzeugt je Besuch eine isolierte SQLite-Arbeitskopie,
bindet Rollenwechsel an dieselbe absolute 60-Minuten-Frist und entfernt den
Arbeitsstand bei Ablauf, Reset oder Abmeldung.

## Kritischer Ablauf: Start und Datenmigration

```mermaid
sequenceDiagram
  actor operator as Betreiber:in
  participant platform as Containerplattform
  participant app as Autoritativer Backendprozess
  participant socket as Admin-Socket
  participant http as HTTP und Frontend
  participant data as SQLite und /data

  operator->>platform: freigegebenes lzug-app wählen und Container ersetzen
  platform->>app: Prozess starten
  app->>data: Konfiguration, Schema und Upgradepfad prüfen
  alt normaler kompatibler Start
    app->>http: live und ready
    app->>socket: Adminaufträge bereitstellen
  else Migration oder Wartung erforderlich
    app->>http: live, not ready und Wartungszustand
    app->>socket: Status, Diagnose und Freigabe bereitstellen
    operator->>socket: Zustand und vollständige Sicherung prüfen
    operator->>socket: Datenmigration ausdrücklich freigeben
    socket->>app: versionierten Auftrag übergeben
    app->>data: Migration unter zentraler Sperre und Transaktion ausführen
    alt Migration erfolgreich
      app->>http: ready schalten
      app-->>socket: Erfolg und Auftrags-ID
    else Migration fehlgeschlagen
      app->>http: live und not ready halten
      app-->>socket: diagnostizierbarer Fehler und Auftrags-ID
    end
  end
```

Die Containerplattform verantwortet Imagewechsel und Prozessstart, nicht die
lzug-Datenmigration.
Der bereits laufende Backendprozess erkennt den Migrationsbedarf, bleibt für
zulässige Adminaufträge erreichbar und führt die vom Betreiber freigegebene
Migration selbst aus.
Ein CLI-Verbindungsabbruch wiederholt keinen verändernden Auftrag; Zustand und
Auftrags-ID ermöglichen nach Wiederanlauf die eindeutige Diagnose.

## Kritischer Ablauf: Plan bestätigen

```mermaid
sequenceDiagram
  actor member as Mitglied
  participant spa as Angular SPA
  participant http as FastAPI
  participant auth as AuthN/AuthZ
  participant plan as Planung
  participant db as SQLite
  participant calendar as Kalender
  participant notification as Hinweise

  member->>spa: Plan bestätigen
  spa->>http: Bestätigungsrequest mit Session und CSRF
  http->>auth: Session, CSRF und Managementrecht prüfen
  auth->>db: aktive Mitgliedschaft lesen
  db-->>auth: Actor und Ausschuss-Scope
  auth-->>http: autorisiert
  http->>plan: Plan bestätigen
  plan->>db: Invarianten prüfen und atomar speichern
  db-->>plan: Commit
  plan-->>http: bestätigter Plan
  http->>calendar: persönliche Kalender synchronisieren
  alt Kalender erfolgreich
    calendar->>db: Kalenderzustand speichern
  else Kalender fehlgeschlagen
    calendar-->>http: Warnung, Fach-Commit bleibt bestehen
  end
  http->>notification: interne Hinweise best effort
  alt Hinweise erfolgreich
    notification->>db: Hinweise speichern
  else Hinweise fehlgeschlagen
    notification-->>http: Warnung, Fach-Commit bleibt bestehen
  end
  http-->>spa: bestätigter Zustand und mögliche Warnung
```

Session, CSRF und Ausschussrecht werden vor der Fachoperation geprüft.
Planungsinvarianten und Statuswechsel liegen in der fachlichen Transaktion.
Kalender- und Benachrichtigungsfolgen laufen danach getrennt; ihre Fehler sind
sichtbar und wiederholbar, rollen den bestätigten Plan aber nicht zurück.

## Architekturprinzipien

1. **Modularer Monolith vor verteilter Komplexität.** Fachliche Module bleiben
   im gemeinsamen Anwendungskern getrennt, solange unabhängige Auslieferung
   keinen belegten Nutzen hat.
2. **Eine Instanz, ein Ausschuss, ein lokaler Betriebsbereich.**
   Ausschussdaten und fachliche Rollen bleiben instanzbezogen;
   Betreiberrechte ersetzen keine Mitgliedschaft.
3. **Verträge sind an jeder Außengrenze explizit.** OpenAPI, Admin-JSON,
   OCI-Konfiguration, Schema, Migrationen und Artefaktformate sind
   überprüfbare Verträge.
4. **Der Anwendungskern bleibt von Adaptern unabhängig.** HTTP, Persistenz,
   Benachrichtigung, Kalender und CLI übersetzen an klaren Grenzen und
   duplizieren keine Fachlogik.
5. **Datenhaltung entwickelt sich vorwärts und erhält Nachweise.**
   Schemaänderungen verwenden geordnete Migrationen; fachliche Versionen und
   Korrekturen überschreiben frühere Stände nicht stillschweigend.
6. **Sicherheitsgrenzen sind serverseitig und fail-closed.** Identität, CSRF,
   Ausschuss-Scope, Rollen, Betreiberzugriff, Uploads und Konfiguration werden
   an der kontrollierenden Grenze validiert.
7. **Externe Integrationen gefährden keinen bestätigten Fachzustand.**
   Kalender, Push und E-Mail sind idempotent oder best effort entkoppelt.
8. **Daten werden minimiert und Änderungen bleiben nachvollziehbar.**
   Schnittstellen, Logs, Diagnosen und Integrationen geben nur den für Zweck
   und Empfänger notwendigen Inhalt aus.
9. **Jeder Gegenstand hat eine maßgebliche Quelle.** Ausführbarer Code,
   deklarative Verträge, ADRs, Handbuch, Wiki und GitHub-Artefakte behalten
   klar getrennte Zuständigkeiten.
10. **Prüftiefe folgt Risiko und Auswirkungsbreite.** Eng begrenzte Änderungen
    erhalten fokussierte Nachweise; Verträge, Sicherheit, Migrationen,
    Toolchain und Querschnittsänderungen benötigen breitere Prüfung.

## Querschnittliche Grenzen

**Authentifizierung und Autorisierung:** Kontenidentität, Betreiberstatus,
Person und Ausschussmitgliedschaft sind getrennt.
Opaque Sessions, sichere Cookies, CSRF, Actor-Auflösung und fachliche Scopes
werden serverseitig durchgesetzt.
Kennwort/TOTP, Einladungen und Recovery verwenden kontrollierte lokale
Verträge; Secrets und Token erscheinen weder in URLs noch in Logs.

**Persistenz und Dokumente:** Fachtransaktion, Dokumentablage und
Snapshot-Sperre besitzen eine gemeinsame kontrollierte Grenze.
Migrationen laufen vorwärts, und Restore aktiviert Datenbank, Dokumente und
Authentifizierungsschlüssel erst nach vollständiger Vor- und Nachprüfung.
Die CLI legt die age-Hülle um den Backend-Paketstrom; private Identitäten
verlassen den Bedienrechner nicht.

**Betrieb und Observability:** Health ist nur Liveness, Ready prüft
Anwendungsbereitschaft, und `lzug-admin system doctor` ergänzt lokale Schema-,
Konfigurations-, Persistenz- und Speicherprüfungen.
Diagnosen, strukturierte Ereignisse und Workflow-Zusammenfassungen bleiben
geheimnisfrei; sie belegen ohne entsprechende Evidenz keinen produktiven
Betriebszustand.

**Öffentliche Demo:** Die Demo verwendet ein unveränderliches App-/Seed-Paar,
flüchtigen Zustand und synthetische Daten.
Die fachlichen Demo-Szenarien laufen in regulären Produktansichten gegen einen
besucherspezifischen Arbeitsstand; produktive Autorisierung und eine enge
rollen- und zustandsgebundene Demo-Allowlist müssen gemeinsam erfüllt sein.
Benachrichtigungen bleiben intern, persönliche Kalenderereignisse sind nur als
eigene Einzeltermine abrufbar und externe Zustellung ist deaktiviert.
OIDC, Environment-Gates, Readiness und Smoke grenzen die technische Promotion
ab; sie begründen keine Produktivitätszusage.

## Risikobasierte Architekturprüfung

- Bleiben Systemgrenze, Verantwortungen und betroffene ADRs
  widerspruchsfrei, oder ist eine neue langfristige Entscheidung nötig?
- Sind Abhängigkeiten, Transaktionen, Seiteneffekte und Fehlerpfade mit ihren
  Auswirkungen beschrieben?
- Bleiben Identität, Ausschuss-Scope, Datenminimierung und Betreibergrenzen
  serverseitig durchgesetzt?
- Sind Migration, Kompatibilität, Wiederanlauf sowie gegebenenfalls Backup und
  Restore nachvollziehbar?
- Passen Konfiguration, Deployment, Readiness, Diagnose und Rückfallgrenze zum
  Betriebsmodell?
- Decken Tests und Dokumentation das konkrete Risiko und die betroffenen
  Schichten ab?

Der [OWASP Application Security Verification Standard](https://github.com/OWASP/ASVS)
wird nur bei berührten Anwendungssicherheitsrisiken herangezogen.
Das [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/what-is-well-architected-framework)
ist nur für Änderungen an der Azure-Demo relevant.
Eine pauschale Konformität wird nicht behauptet.

Langfristige Entscheidungen stehen ausschließlich im
[ADR-Register](decisions/index.md).
Ein ADR erklärt Richtung, Alternativen und Konsequenzen, nicht aktuelle
Routen-, Feld- oder Workflowdetails.
