# Architekturansichten

Diese Sichten verwenden C4-Begriffe und C4-Abstraktionsebenen in stabiler Mermaid-`flowchart`-Syntax.
Sie zeigen Orientierung und bewusste Grenzen, keine vollständige Inventarliste aller Klassen, Tabellen, Routen oder Azure-Ressourcen.
Die ausführbaren Quellen und die verlinkten Detailseiten bleiben maßgeblich.

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

Fachliche Arbeit ist immer auf aktive Mitgliedschaften des Ausschusses begrenzt.
Betreiberzugriffe bleiben lokal und verleihen keine fachlichen Rechte.
Push-Dienst und SMTP-Relay sind optionale technische Kanäle; ohne sie bleibt der interne Hinweis erhalten.
Eine zentrale IHK-Plattform oder ein externer Identitätsprovider gehört derzeit nicht zum laufenden System.

## Container-Sicht

Im C4-Sinn bezeichnet ein Container hier eine laufende Anwendung oder einen Datenspeicher, nicht nur einen OCI-Container.

```mermaid
flowchart LR
  member["Person: Ausschussmitglied"]
  operator["Person: Betreiber:in"]
  channels["Externe Software Systeme:<br/>Push-Dienst und SMTP-Relay"]

  subgraph system["Software System: lzug"]
    spa["Container: Angular SPA<br/>Browser-Oberfläche"]
    app["Container: Python/FastAPI-Anwendung<br/>HTTP, Sicherheit, Anwendungskern<br/>und Integrationsadapter"]
    admin["Container: lzug-admin<br/>portable Go-CLI"]
    data[("Container: SQLite und /data<br/>Fachdaten, Dokumente,<br/>Schlüssel und Backups")]
  end

  member -->|"bedient"| spa
  spa -->|"same-origin JSON/HTTPS"| app
  operator -->|"lokaler CLI-Aufruf"| admin
  admin -->|"versioniertes JSON via Container-Engine exec"| app
  app -->|"SQLAlchemy und Dateizugriff"| data
  app -.->|"best effort"| channels
```

Das Browser-Bundle und die Python-Anwendung werden gemeinsam im OCI-Image ausgeliefert, bleiben aber getrennte C4-Container mit einer HTTP-Grenze.
Die Python-Anwendung hält HTTP, Authentifizierung, frameworkfreie Anwendungsservices, Repositories und Integrationsadapter in einem Prozess.
Die [Backend-Übersicht](backend.md) beschreibt diese internen Komponenten, ohne sie fälschlich als unabhängig deploybare Dienste darzustellen.
`lzug-admin` kennt weder SQLite noch SQLAlchemy; es ruft das versionierte lokale Admin-Protokoll im laufenden Anwendungscontainer auf.

## Deployment-Sicht

```mermaid
flowchart TB
  member["Person: Ausschussmitglied"]
  operator["Person: Betreiber:in"]

  subgraph host["Deployment Node: Self-Hosting-Host"]
    tls["Deployment Node: betreiberseitiger TLS-Endpunkt<br/>optional und nicht Teil des Images"]
    admin["Executable: lzug-admin"]

    subgraph engine["Deployment Node: Docker oder Podman"]
      app["Container-Instanz: lzug OCI-Image<br/>UID/GID 10001, Port 8000,<br/>read-only Root-Dateisystem"]
      data[("Volume: /data<br/>SQLite, Dokumente,<br/>Schlüssel und Backups")]
    end
  end

  member -->|"HTTPS"| tls
  tls -->|"HTTP an Port 8000"| app
  operator -->|"lokaler Aufruf"| admin
  admin -->|"engine exec"| app
  app -->|"einziger dauerhafter Schreibbereich"| data
```

Das Diagramm zeigt die unterstützte Self-Hosting-Grenze einer Instanz.
TLS-Terminierung, Host-Härtung, Sicherung und Wiederherstellung liegen in der Betreiberverantwortung und werden nicht durch das Image erfunden.
Der Container kann mit schreibgeschütztem Root-Dateisystem laufen; `/data` trägt den gesamten dauerhaften Zustand einschließlich des lokalen Authentifizierungsschlüssels.
Details stehen im [OCI-Runtime-Vertrag](oci-runtime.md).
Die [öffentliche Demo](../demo-deployment.md) ist eine separate flüchtige Azure-Assembly mit synthetischen Daten und kein Vorbild für persistentes Self-Hosting.

## Kritischer Ablauf: Plan bestätigen

Die Planbestätigung zeigt die zentrale Sicherheits- und Transaktionsgrenze sowie die bewusste Entkopplung technischer Folgen.

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
  spa->>http: POST /api/exam-rounds/{id}/confirm-plan<br/>Session und CSRF
  http->>auth: Session, CSRF und Managementrecht
  auth->>db: aktive Mitgliedschaft lesen
  db-->>auth: Actor und Ausschuss-Scope
  auth-->>http: autorisiert
  http->>plan: confirm_plan(round_id)
  plan->>db: Invarianten prüfen<br/>Plan atomar bestätigen
  db-->>plan: Commit
  plan-->>http: bestätigter Plan
  http->>calendar: persönliche Kalender
  alt Kalendersynchronisierung erfolgreich
    calendar->>db: Kalenderereignisse speichern
    db-->>calendar: Ergebnis
    calendar-->>http: synchronisiert
  else Kalendersynchronisierung fehlgeschlagen
    calendar-->>http: Fehler, Fach-Commit bleibt bestehen
  end
  http->>notification: interne Hinweise best effort
  alt Hinweise erzeugt
    notification->>db: Hinweise speichern
    db-->>notification: Ergebnis
    notification-->>http: erzeugt
  else Hinweiserzeugung fehlgeschlagen
    notification-->>http: Warnung, Fach-Commit bleibt bestehen
  end
  http-->>spa: bestätigter Zustand, gegebenenfalls Warnung
  spa-->>member: Ergebnis anzeigen
```

Session, CSRF und Ausschussrecht werden vor der Fachoperation geprüft.
Die Planungsinvarianten und der Statuswechsel werden in der fachlichen Transaktion bestätigt.
Kalender- und Benachrichtigungsfolgen laufen danach best effort; ein Fehler bleibt sichtbar, rollt den bestätigten Plan aber nicht zurück.
Die spätere technische Zustellung wird getrennt durch `lzug-admin process-notifications` verarbeitet und kann keine Exactly-once-Garantie gegenüber externen Kanälen geben.
