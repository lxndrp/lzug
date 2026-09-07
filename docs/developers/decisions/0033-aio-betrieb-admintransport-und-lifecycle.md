# ADR-0033: AIO-Betrieb, Admintransport und Lifecycle gemeinsam begrenzen

## Datum

2026-09-07.

## Status

Akzeptiert.

## Kontext

Das produktive Self-Hosting bündelt Browser-Anwendung, Python-Backend und lokale
Persistenz in einer Instanz mit einem persistenten `/data`.
Öffentliche HTTP-Zugriffe und administrative Aufträge benötigen verschiedene
Authentisierungs- und Autorisierungsgrenzen, greifen aber auf denselben
Anwendungszustand zu.

Ein getrennter dauerhaft laufender Adminprozess würde neben dem Webprozess auf
dieselbe SQLite- und Dateipersistenz zugreifen.
Schemawechsel, Transaktionen, Sperren, Wartungszustände und Wiederanlauf müssten
dann zwischen unabhängigen Prozessen koordiniert werden.
Auch ein eigener Migrationsprozess würde eine zweite persistenzführende Instanz
und damit eine vermeidbare Fehler- und Zustandsgrenze schaffen.

Zugleich müssen die Zuständigkeiten von Containerplattform, Backend und
Betreiber-CLI eindeutig bleiben.
Das OCI-Image soll portabel sein, ohne jede OCI-Laufzeit als unterstützt zu
deklarieren oder die Anwendungsadministration an eine Container-Engine zu
binden.

## Entscheidung

### Prozess-, Persistenz- und Transportgrenze

Das produktive OCI-Image heißt `lzug-app`.
Im gestarteten Produktcontainer läuft genau ein autoritativer Backendprozess.
Nur dieser Prozess koordiniert SQLite, Dokumente, Sicherungen, Migrationen,
Transaktionen, Sperren und den Anwendungs-Lifecycle.

Der Prozess bindet zwei Transportadapter an denselben Anwendungskern:

- den öffentlichen HTTP-Adapter für Browser und Plattformprobes;
- einen gehärteten lokalen Adminadapter über einen Unix-Domain-Socket.

Der Adminadapter ist kein eigener Prozess und besitzt keinen Netzwerk-Listener.
HTTP- und Socketadapter verwenden dieselben Anwendungsservices und
Transaktionsgrenzen, ohne Fach-, Persistenz- oder Lifecyclelogik zu duplizieren.
Der Socket liegt in einem flüchtigen Laufzeitverzeichnis und wird nur nach
Prüfung von Eigentümer, Rechten, Dateityp und Symlinkgrenze veröffentlicht.

Fachliche Webberechtigungen und Betreiberberechtigungen bleiben getrennte
Vertrauensgrenzen.
Der HTTP-Adapter erzwingt Session, CSRF und fachlichen Ausschuss-Scope.
Der Adminadapter autorisiert über die lokale Betriebssystemgrenze und prüft die
Peer-Identität, soweit die Zielplattform dies zuverlässig bereitstellt.
Eine Betreiberberechtigung verleiht keine fachliche Mitgliedschaft; vom Client
behauptete Identitätsdaten begründen keine Autorisierung.

### Einheitlicher CLI-Zugriff

Die portable CLI verwendet lokal den Unix-Domain-Socket direkt.
Ein externer Aufruf verwendet die vorhandene System-OpenSSH-Implementierung und
leitet exakt denselben Socketvertrag weiter.
Auf dem Zielhost wird kein lzug-Adminport veröffentlicht, und im Container
läuft weder ein SSH-Dienst noch eine entfernte CLI-Bridge.
SSH-Authentisierung, Hostprüfung, Identitätswahl, Agent und Sprunghost bleiben
in der Verantwortung von OpenSSH und der Betreiberkonfiguration.

Direkte Befehle verwenden `lzug-admin <objekt> <aktion>`; der interaktive
Einstieg verwendet `lzug-admin cli`.
Beide Wege nutzen dieselbe Registry, Validierung, Auftragsbildung und
Ergebnisinterpretation.
Auch ein durch die Containerplattform im Produktcontainer gestartetes
CLI-Binary spricht anschließend den lokalen Socket direkt an.
Es gibt kein Helper-Skript, keine abweichende Containeroberfläche und keinen
automatischen Fallback zwischen Socket, SSH und Container-Engine.

Private Schlüssel für geschützte Sicherungs-, Restore- oder Exportartefakte
bleiben gemäß ADR-0031 auf dem Bedienrechner.
Der Admintransport überträgt nur den erforderlichen Klartext-Paketstrom und den
strukturierten Auftrag; private Schlüssel und Passphrasen gelangen weder zum
Backend noch in Argumente, Umgebung, Ausgaben, Audit oder Logs.
Das serverseitige Audit beschränkt sich auf die technisch verifizierte
Betriebssystemidentität, Befehlsklasse, Beginn und Ende, Ergebnis oder
Fehlerphase sowie Korrelations- und Auftrags-ID.
Parameter und fachliche Nutzdaten werden nicht protokolliert.

### Lifecycle und Migration

Der autoritative Prozess unterscheidet mindestens Initialisierung, normalen
Betrieb, Wartung, erforderliche Migration, laufende Migration und einen
diagnostizierbaren Fehlerzustand.
Er bleibt in allen diesen Zuständen live.
Ready ist er nur, wenn Konfiguration, Persistenz und Schema kompatibel sind und
normale Fachaufträge sicher ausgeführt werden können.

Während Initialisierung, Wartung und Migration bleibt der Admin-Socket für
zulässige Status-, Diagnose- und Freigabeaufträge erreichbar.
Readiness ist negativ, normale Fachaufträge werden fail-closed abgewiesen und
der HTTP-Adapter stellt statt einer regulären Anwendung einen knappen
Wartungszustand bereit.
Liveness, Readiness, Frontend und CLI leiten ihre Darstellung aus demselben
Lifecyclezustand ab.

Die Containerplattform bezieht das Image, ersetzt und startet den Container.
Sie führt keine lzug-Datenmigration aus.
Der Backendprozess erkennt einen Migrationsbedarf und weist Upgradepfad,
Sicherungsanforderung und Rollbackgrenze über den Adminvertrag aus.
Der Betreiber prüft den Zustand und genehmigt die Datenmigration ausdrücklich
über die CLI.
Genau derselbe bereits laufende Backendprozess führt die Migration unter seiner
zentralen Transaktions-, Sperr- und Lifecyclekoordination aus.

Nach vollständigem Erfolg wechselt der Prozess zu ready.
Bei Fehler oder Neustart bleibt das Ergebnis über Zustand und Auftrags-ID
diagnostizierbar; der Prozess nimmt keinen normalen Betrieb mit unklarem oder
inkompatiblem Schema auf.
Ein Verbindungsabbruch führt nicht zur automatischen Wiederholung eines
verändernden Auftrags.
Ein Image-Rollback bleibt Aufgabe der Containerplattform, während lzug nur die
Daten- und Schemakompatibilität sowie einen zulässigen Restore- oder
Vorwärtsweg bewertet.

### Image- und Plattformgrenze

Die öffentliche Demo wird als getrenntes Image `lzug-demo` ausgeliefert und
bleibt eine flüchtige Assembly mit synthetischen Daten.
Sie ist kein Self-Hosting-Muster und teilt keine produktive Persistenz mit
`lzug-app`.

Das OCI-Image ist die portable Liefergrenze.
Docker Engine auf Linux ist die qualifizierte Referenz für Build, Release, CI
und Self-Hosting.
Andere OCI-Laufzeiten können das Image ausführen, gehören daraus aber nicht
automatisch zum unterstützten oder geprüften Umfang.
Podman wird nicht unterstützt oder geprüft.

Compose bleibt ein optionaler, knapper Docker-Referenzweg für genau den einen
`lzug-app`-Service mit persistentem `/data`.
Es ist weder eine zweite Produktbeschreibung noch eine plattformneutrale
Orchestrierungsabstraktion.
Apple `container` und Microsoft `wslc` sind keine aktuellen Referenzen,
Supportversprechen oder Release-Gates.

## Konsequenzen

- Persistenz- und Lifecycleentscheidungen besitzen genau einen Prozess als
  autoritative Schreib- und Zustandsgrenze.
- HTTP und lokaler Adminzugriff können unterschiedliche Vertrauensgrenzen
  erzwingen, ohne Anwendungslogik oder Transaktionen auf Prozesse aufzuteilen.
- Die Adminschnittstelle bleibt lokal; externer Zugriff übernimmt die
  etablierte Sicherheits- und Konfigurationsgrenze von System-OpenSSH.
- Plattformprobes, Frontend und CLI dürfen einen live, aber nicht ready
  befindlichen Zustand nicht als Ausfall oder einsatzbereiten Normalbetrieb
  fehlinterpretieren.
- Imagewechsel und Prozessstart bleiben von Prüfung, Freigabe und Ausführung
  einer Datenmigration getrennt.
- `lzug-app` und `lzug-demo` haben eindeutige, unterschiedliche
  Lieferverantwortungen.
- Docker-spezifische Referenzprüfung schränkt die OCI-Portabilität des
  Produktimages nicht ein, begründet aber auch kein Supportversprechen für
  weitere Laufzeiten.
- ADR-0014 behält den Einzelcontainer- und `/data`-Vertrag bei; ADR-0017 behält
  die Entscheidung gegen Kubernetes und Helm als Pflichtpfad bei.

## Alternativen

- **Separater dauerhafter Adminprozess:** würde Persistenz, Transaktionen,
  Sperren, Schema und Lifecycle zwischen zwei Backendprozessen koordinieren.
- **Paralleler Migrationsservice:** würde während des empfindlichsten
  Zustandsübergangs eine zweite persistenzführende Autorität schaffen.
- **Admin-Netzwerkport:** würde eine zusätzliche öffentlich zu härtende
  Produkt-, Authentisierungs- und Angriffsgrenze eröffnen.
- **SSH-Dienst im Container:** würde Betriebssystemfunktion duplizieren und
  Schlüssel-, Patch- und Prozessverantwortung in das Produktimage ziehen.
- **Container-Engine als Admintransport:** würde die CLI an privilegierte,
  plattformspezifische Engine-Schnittstellen und deren Prozessmodell koppeln.
- **Helper-Wrapper oder abweichende Container-CLI:** würde einen zweiten
  Bedien- und Fehlervertrag neben `lzug-admin` erzeugen.
- **Mehrere gleichrangige Referenzruntimes:** würde Support und Quality-Gates
  verbreitern, ohne die OCI-Liefergrenze zu verbessern.

## Referenzen

- [Architekturübersicht](../architecture.md)
- [Komponenten](../components.md)
- [ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`](0014-oci-einzelcontainer-und-persistentes-data.md)
- [ADR-0017: Erstveröffentlichung ohne Kubernetes und Helm](0017-erstveroeffentlichung-ohne-kubernetes.md)
- [ADR-0031: age-Hülle in der Betreiber-CLI](0031-age-huelle-in-der-betreiber-cli.md)
