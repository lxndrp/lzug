# ADR-0033: AIO-Betrieb, Admintransport und Lifecycle gemeinsam begrenzen

## Datum

2026-09-07.
Präzisierung der Socket-Zuständigkeitsgrenze am 2026-09-11 in #581.

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

Die portable CLI verwendet einen bereitgestellten lokalen Socket-Endpunkt.
Client und Server kennen ausschließlich den Socket-Zugriff und denselben
versionierten Adminvertrag.
Die Bereitstellung des Endpunkts und ein möglicher entfernter Transport liegen
außerhalb der Applikation.
Konfiguration und CLI benötigen dafür keinen Transportumschalter oder
Parameter für entfernte Hosts und Weiterleitungen.
Tests und zugesicherte Eigenschaften enden an der Socket-Schnittstelle.
Ein Betriebsbeispiel darf eine externe Weiterleitung beschreiben, ohne sie zum
unterstützten oder geprüften Produktbestandteil zu erklären.
Auf dem Zielhost wird kein lzug-Adminport veröffentlicht.

Direkte Befehle verwenden `lzug-admin <objekt> <aktion>`; der interaktive
Einstieg verwendet `lzug-admin cli`.
Beide Wege nutzen dieselbe Registry, Validierung, Auftragsbildung und
Ergebnisinterpretation.
Die separat ausgelieferte CLI spricht den lokalen Socket direkt an.
Es gibt kein Helper-Skript, keine abweichende Containeroberfläche und keinen
automatischen Wechsel des konfigurierten Endpunkts.

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
Docker Engine auf Linux bleibt die qualifizierte Referenz für zentrale CI,
Release und Self-Hosting.
Diese Betriebsreferenz ist unabhängig von den lokalen Build- und
Prüfplattformen und erweitert sich nicht automatisch mit ihnen.

Für lokale Entwicklung ist die Zielreihenfolge plattformbezogen:

| Ausführungskontext | Bevorzugte lokale Runtime | Fallback |
| --- | --- | --- |
| macOS mit Apple Silicon | Apple `container` | Docker |
| Linux | rootless Podman | Docker |
| Windows-Host | Microsoft `wslc` | Docker |
| WSL-Linux-Shell | Linux-Hostauswahl: Podman, sofern installiert | Docker |

Diese Tabelle legt die Zielauswahl fest, behauptet aber keine bereits
abgeschlossene Plattformqualifikation.
Apple `container`, Podman und `wslc` gehören erst dann zum nutzbaren lokalen
Build-/Prüfumfang, wenn die jeweiligen Hostnachweise aus #939, #940 und #941
vorliegen.
Ein Linux-Prozess in WSL wird nicht allein wegen einer erreichbaren
`wslc.exe` als Windows-Host behandelt; Windows- und WSL-Pfade, Dateirechte und
Benutzerzuordnung sind getrennte Ausführungskontexte.

Die Runtimeauswahl erfolgt nur einmal für einen Tasklauf.
Ein expliziter Override wählt genau die angegebene Runtime; ist sie nicht
installiert oder nicht verfügbar, wird mit Diagnose abgebrochen.
In `auto` darf Docker nur verwendet werden, wenn die bevorzugte Runtime des
Ausführungskontexts nicht installiert ist.
Eine installierte, aber nicht erreichbare Runtime, ein Buildfehler oder ein
Fehler beim Starten eines Containers löst keinen Wechsel zu Docker aus.
So bleiben Infrastruktur- und Produktfehler sichtbar.

Die gemeinsamen lokalen Builds verwenden unveränderte Dockerfiles und den
nativen `linux/<arch>`-Zielpfad des Hosts.
Build-Identität und vollständige Git-Revision bleiben über die vorhandenen
Build-Argumente und OCI-Labels gebunden.
Jeder Buildkandidat wird einmal erzeugt; SBOM und Laufzeittest verwenden
anschließend dasselbe Artefakt.
Für eine SBOM wird das tatsächlich gebaute Image explizit als Image-Archiv
exportiert und aus diesem Archiv mit der versionierten Syft-Konfiguration
gescannt.
Der Laufzeittest verwendet dasselbe gebaute Image; ein impliziter Zugriff auf
einen Docker-Imagespeicher oder ein zweiter Build ist kein zulässiger
Übergabevertrag.
Das Demo-Seed wird ausdrücklich aus dem Seed-Artefakt entnommen; die
plattformbezogene Methode dafür wird im Runtime-Pilot nachgewiesen, statt
`docker create`/`docker cp` als universellen Vertrag vorauszusetzen.

Die gemeinsamen Laufzeitnachweise umfassen Image- und Buildidentität,
Readiness, Daten-Roundtrip und Persistenz bei Restart/Stop-Start, UID/GID,
read-only Root-Dateisystem, Admin-Socket-Eigentum und -Modus sowie die
ausgelieferte CLI.
Ein fehlender oder abweichender Plattformmechanismus darf diese Prüfungen
nicht abschwächen.
Docker Compose, seine Konfigurationsprüfung sowie Docker-basierte
Veröffentlichungs- und CI-Schritte bleiben ausdrücklich Docker-spezifische
Referenzprüfungen.

Temporäre Ressourcen eines Worktree-Tests werden nach dem Scope benannt:
`lzug-codex-<scope>-<rolle>`.
Container, Images, Volumes und Netzwerke erhalten zusätzlich genau das
Worktree-Label `lzug-codex-<scope>` ohne separates Label-Value-Schema.
Der Scope kommt aus `LZUG_DEVELOPMENT_RESOURCE_SCOPE`; Task konsumiert ihn,
ohne Codex als Voraussetzung zu machen.
Jede Runtime-Qualifikation muss belegen, dass dieses Label für die erstellten
Ressourcentypen gesetzt, abgefragt und für gezieltes Cleanup verwendet werden
kann.
Cleanup entfernt ausschließlich Ressourcen mit dem exakten Label und dem
erwarteten Namenspräfix; kein globales `prune` oder Entfernen fremder Volumes
ist zulässig.

Compose bleibt ein optionaler, knapper Docker-Referenzweg für genau den einen
`lzug-app`-Service mit persistentem `/data`.
Es ist weder eine zweite Produktbeschreibung noch eine plattformneutrale
Orchestrierungsabstraktion.

## Konsequenzen

- Persistenz- und Lifecycleentscheidungen besitzen genau einen Prozess als
  autoritative Schreib- und Zustandsgrenze.
- HTTP und lokaler Adminzugriff können unterschiedliche Vertrauensgrenzen
  erzwingen, ohne Anwendungslogik oder Transaktionen auf Prozesse aufzuteilen.
- Die Adminschnittstelle bleibt lokal; Bereitstellung und entfernte
  Transportwege bleiben in der Verantwortung des Betreibers.
- Plattformprobes, Frontend und CLI dürfen einen live, aber nicht ready
  befindlichen Zustand nicht als Ausfall oder einsatzbereiten Normalbetrieb
  fehlinterpretieren.
- Imagewechsel und Prozessstart bleiben von Prüfung, Freigabe und Ausführung
  einer Datenmigration getrennt.
- `lzug-app` und `lzug-demo` haben eindeutige, unterschiedliche
  Lieferverantwortungen.
- Die lokale Runtimeauswahl verändert weder die Docker-Referenz für zentrale
  CI, Release und Self-Hosting noch die fachlichen, Persistenz- und
  Sicherheitsverträge der Images.
- Eine lokale Runtime wird erst nach einem realen Build-, Laufzeit- und
  Cleanup-Nachweis als qualifiziert dokumentiert.
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
