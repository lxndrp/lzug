# ADR-0043: Lokale OCI-Runtimeauswahl und Plattformqualifikation

## Datum

2026-10-26.

## Status

Akzeptiert.

## Kontext

Die Produktimages sind OCI-Artefakte. Für zentrale CI, Release und
Self-Hosting bleibt Docker Engine auf Linux die qualifizierte Referenz.
Lokale Entwicklungsbuilds und Laufzeitprüfungen sollen auf die native Runtime
der jeweiligen Entwicklerplattform zurückgreifen können, ohne damit eine
weitere Produktiv- oder Releaseplattform zu versprechen.

Der Runtimevertrag muss außerdem sicherstellen, dass Imageidentität,
Buildrevision, SBOM, Laufzeitnachweis und bereinigte Ressourcen demselben
Buildkandidaten zugeordnet bleiben. Ein Fehler einer ausdrücklich gewählten
oder installierten Runtime darf nicht durch einen stillen Docker-Wechsel
verdeckt werden.

ADR-0033 legt die gemeinsame Prozess-, Persistenz-, Admintransport- und
Lifecyclegrenze fest. Seine Aussagen zur Laufzeitreferenz und zu nicht
unterstützten zusätzlichen Runtimes gelten weiterhin für zentrale CI, Release
und Self-Hosting; diese ADR ergänzt ausschließlich lokale Entwicklungs- und
Prüfplattformen.

## Entscheidung

### Lokale Runtimeauswahl

Für lokale Entwicklungsbuilds und Laufzeitprüfungen gilt diese
plattformbezogene Zielauswahl:

| Ausführungskontext | Bevorzugte lokale Runtime | Fallback |
| --- | --- | --- |
| macOS mit Apple Silicon | Apple `container` | Docker |
| Linux | rootless Podman | Docker |
| Windows-Host | Microsoft `wslc` | Docker |
| WSL-Linux-Shell | Linux-Auswahl: Podman, sofern installiert | Docker |

Apple `container`, Podman und `wslc` dürfen erst nach erfolgreicher
Qualifikation auf einem echten Host als nutzbare lokale Runtime gelten. Die
Nachweise werden getrennt in #939, #940 und #941 geführt. Eine WSL-Linux-Shell
wird anhand ihres Linux-Prozesskontexts ausgewählt; eine erreichbare
`wslc.exe` macht sie nicht zum Windows-Host.

`CONTAINER_ENGINE` akzeptiert `auto`, `podman`, `apple`, `wslc` oder `docker`.
Ohne gesetzten Wert gilt `auto`:

| Wert | Ausgewählte Runtime |
| --- | --- |
| `auto` | Bevorzugte Runtime des Ausführungskontexts |
| `podman` | Podman |
| `apple` | Apple `container` |
| `wslc` | Microsoft `wslc` |
| `docker` | Docker |

Ein unbekannter Wert bricht vor Ressourcenänderungen mit einer Diagnose ab.
Die Auswahl erfolgt einmal je Tasklauf. Eine explizit gewählte Runtime, die
nicht installiert oder nicht erreichbar ist, führt zum Abbruch. In `auto`
darf Docker nur gewählt werden, wenn die bevorzugte Runtime fehlt. Ein
unerreichbarer Dienst, Buildfehler oder Containerstartfehler führt nicht zum
Runtimewechsel.

### Buildartefakte und Prüfvertrag

Gemeinsame lokale Builds verwenden die bestehenden Dockerfiles und das native
`linux/<arch>`-Ziel des Hosts. Buildidentität und vollständige Gitrevision
bleiben an den vorhandenen Buildargumenten und OCI-Labels gebunden. Der
Runtimevertrag erstellt den Buildkandidaten einmal. Die SBOM und der
zugehörige Laufzeit- oder Integrationsnachweis beziehen sich auf genau dieses
Artefakt:

| Image | SBOM-Nachweis | Laufzeit- und Integrationsnachweis |
| --- | --- | --- |
| `lzug-app` | Aus dem Archiv des gebauten Images | Gemeinsamer App-Runtimevertrag mit genau diesem Image |
| `lzug-demo-app` | Aus dem Archiv des gebauten Images | Demo-Runtimevertrag mit genau diesem Image und dem zugehörigen Seed |
| `lzug-demo-seed` | Aus dem Archiv des gebauten Images | SQLite-Datei und Manifest aus genau diesem Image extrahieren und Identität, Produktrevision, Runtimevertrag sowie Schemafingerabdruck prüfen; Seed nicht als eigenständigen Server starten |

Ein impliziter Zugriff auf einen enginespezifischen Imagespeicher oder ein
zweiter Build ist kein Übergabevertrag. Der Demo-Runtime-Nachweis verwendet
den extrahierten Seed mit dem zugehörigen `lzug-demo-app`-Image. Die
plattformspezifische Extraktionsmethode wird im jeweiligen Runtime-Pilot
nachgewiesen. Für die SBOM wird das gebaute Image als Archiv exportiert und
mit der versionierten Syft-Konfiguration gescannt.

Gemeinsame Laufzeitnachweise umfassen Image- und Buildidentität, Readiness,
Daten-Roundtrip und Persistenz bei Restart/Stop-Start, UID/GID, read-only
Root-Dateisystem, Admin-Socket-Eigentum und -Modus sowie die ausgelieferte
CLI. Ein fehlender oder abweichender Plattformmechanismus darf diese
Prüfungen nicht abschwächen. Docker Compose, seine Konfigurationsprüfung und
Docker-basierte Veröffentlichungs- sowie CI-Schritte bleiben
Docker-spezifische Referenzprüfungen und ersetzen keinen plattformneutralen
Runtime-Nachweis.

### Ressourcen und Cleanup

Temporäre Ressourcen eines Worktree-Tests verwenden Namen der Form
`lzug-codex-<scope>-<rolle>`. Container, Images, Volumes und Netzwerke erhalten
zusätzlich genau das Worktree-Label `lzug-codex-<scope>`. Der Scope kommt aus
`LZUG_DEVELOPMENT_RESOURCE_SCOPE`; Task konsumiert ihn ohne Codex als
Voraussetzung.

Ein Scope enthält mindestens ein kleingeschriebenes ASCII-Zeichen oder eine
Ziffer; weitere Zeichen dürfen kleingeschriebene ASCII-Buchstaben, Ziffern
oder einzelne Bindestriche zwischen nichtleeren Teilen sein. Ressourcen, die
einen Tasklauf überleben oder später bereinigt werden, dürfen nur mit
gesetztem und validiertem Scope angelegt werden. Fehlt er oder ist er
ungültig, bricht Anlage beziehungsweise Cleanup vor Änderungen ab.

Temporäre Test- und Cache-Volumes dürfen das Worktree-Label tragen.
Persistente Anwendungsdatenvolumes bleiben unlabeled und werden beim
Worktree-Cleanup nicht entfernt. Jede Runtime-Qualifikation muss belegen,
dass Labels für erstellte Ressourcentypen gesetzt, abgefragt und für gezieltes
Cleanup verwendet werden können. Cleanup entfernt ausschließlich Ressourcen
mit dem exakten Label und dem erwarteten Namenspräfix. Globales `prune` und
das Entfernen fremder Volumes sind unzulässig.

Compose bleibt ein optionaler, knapper Docker-Referenzweg für genau den einen
`lzug-app`-Service mit persistentem `/data`. Es ist weder eine zweite
Produktbeschreibung noch eine plattformneutrale Orchestrierungsabstraktion.

## Konsequenzen

- Die lokale Runtimeauswahl ändert weder die Docker-Referenz für zentrale CI,
  Release und Self-Hosting noch die fachlichen, Persistenz- und
  Sicherheitsverträge der Images.
- Eine alternative lokale Runtime wird erst nach realem Build-, Laufzeit- und
  Cleanup-Nachweis als qualifiziert dokumentiert.
- Build, SBOM und Runtimeprüfung bleiben über dasselbe exportierte Artefakt
  verbunden.
- Die Worktree-Zuordnung ermöglicht gezieltes Cleanup, ohne globale
  Ressourcenbereinigung oder das Löschen persistenter Anwendungsdaten.
- ADR-0033 bleibt für Prozess, Persistenz, Admintransport und Lifecycle
  maßgeblich.

## Alternativen

- **Docker als einzige lokale Runtime:** würde plattformeigene Werkzeuge und
  deren mögliche Vorteile für Entwickler:innen ungenutzt lassen.
- **Stiller Wechsel zu Docker bei Runtimefehlern:** würde Installations-,
  Dienst- und Buildfehler verdecken und die tatsächliche Plattformprüfung
  unklar machen.
- **Eigenständige Containerabstraktionsplattform:** würde einen zusätzlichen
  Runtime- und Konfigurationsvertrag parallel zu den vorhandenen Werkzeugen
  schaffen.
- **Runtimequalifikation allein durch CI oder Metadaten:** belegt weder
  Hostverhalten noch die plattformspezifische Ressourcen- und
  Artefaktübergabe.

## Referenzen

- [Architekturübersicht](../architecture.md)
- [Komponenten](../components.md)
- [ADR-0033: AIO-Betrieb, Admintransport und Lifecycle gemeinsam begrenzen](0033-aio-betrieb-admintransport-und-lifecycle.md)
- [ADR-0038: SBOM-Erzeugung als direkte Syft-Standardaufrufe](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md)
- [ADR-0040: Buildx-SBOM für Produkt-Snapshots](0040-buildx-sbom-produkt-snapshots.md)
- [Issue #938](https://github.com/lxndrp/lzug/issues/938)
- [Epic #1022](https://github.com/lxndrp/lzug/issues/1022)
