# lzug Codex-Projektanweisung

Diese Datei beschreibt den Arbeitsmodus fuer Codex und andere Coding Agents im Projekt `lzug`.

## Projektkontext

`lzug` ist eine Web-App zur Unterstuetzung eines IHK-Pruefungsausschusses fuer Fachinformatiker-Pruefungen. Die App richtet sich an den Pruefungsausschuss, nicht an festangestellte IHK-Mitarbeitende.

Fachlich gibt es zwei zentrale Epics:

- **Pruefungen planen**: Prueflinge, Ausschussmitglieder, Orte, Verfuegbarkeiten, Planungsvorschlag, Bestaetigung, Ausfallprozess und Terminbereitstellung.
- **Pruefungen durchfuehren**: Tagesansicht, Anwesenheiten, Pruefungsstatus, Protokollierung, Ergebnis-/Abschlussdaten und Abschlusslogik. Dieses Epic ist noch fachlich zu schaerfen.

Der aktuelle fachliche Referenzstand liegt in `docs/fachliche-anforderungen-plan.md`. Das GitHub Project `lzug Roadmap` ist die operative Roadmap.

## Planung und Nachverfolgung

Arbeite nach diesem Modell:

- Chat und lokale Notizen sind Arbeitsgedaechtnis.
- Repository-Dokumente sind versionierter fachlicher Kontext fuer Codex und Entwicklungsentscheidungen.
- GitHub Issues und GitHub Projects sind die dauerhafte Quelle fuer Backlog, Fortschritt und Nachverfolgung.

Wenn fachliche Planung in Codex entsteht und belastbar genug ist, ueberfuehre sie in GitHub:

- Epics als echte GitHub Issues mit Label `type: epic`.
- User Stories als echte GitHub Issues mit Label `type: story`.
- Technische Aufgaben als echte GitHub Issues mit Label `type: task`.
- Nachtraeglich importierte Bestands- oder Entscheidungsdokumentation mit Label `source: baseline-import`.
- Epics und Stories ueber Parent/Sub-Issues verknuepfen.
- Das GitHub Project `lzug Roadmap` fuer Status, Board-Ansicht und Priorisierung nutzen.

Draft-Items im GitHub Project nur fuer sehr fruehe Ideen verwenden. Sobald ein Element handhabbar oder nachvollziehbar sein soll, als Issue anlegen.

## Statusmodell

Im GitHub Project gelten die Standardstatus:

- `Todo`: fachlich aufgenommen, noch nicht begonnen.
- `In Progress`: aktuell in Arbeit oder aktives Epic.
- `Done`: abgeschlossen und nachvollziehbar dokumentiert.

Geschlossene Issues nicht loeschen. Wenn sie aus einer nachtraeglichen Ueberfuehrung stammen, muessen sie transparent als Baseline-Import markiert sein.

## Entwicklungsprozess

- Bestehende Git-Historie und Artefakte bewahren.
- Vor groesseren Aenderungen den aktuellen Repo-Zustand lesen statt aus Erinnerung zu arbeiten.
- Aenderungen thematisch schneiden und kleine, nachvollziehbare Commits bevorzugen.
- Commit-Messages bevorzugt auf Englisch schreiben, passend zur bisherigen Git-Historie; Deutsch und Englisch nicht innerhalb einer Message mischen.
- Keine fremden oder ungefragten Aenderungen zuruecksetzen.
- Wenn der Nutzer Planung statt Umsetzung verlangt, read-only bleiben.
- Wenn der Nutzer Umsetzung verlangt, bis zur Verifikation durchziehen.

## Backend

Das produktive Backend soll keine SQL-Statements im Anwendungscode enthalten. Persistenz und CRUD-Operationen laufen ueber ORM-nahe Abstraktionen, Repositories und REST-nahe Ressourcen.

Bei Erweiterungen:

- Bestehende SQLAlchemy-Modelle und Repository-Muster verwenden.
- Neue fachliche Konzepte zuerst sauber im Domain-/Datenmodell einordnen.
- REST-Schnittstellen so schneiden, dass sie direkt vom Angular-Client nutzbar sind.
- Rechte- und Statusuebergaenge serverseitig testen.

## Frontend

Das Angular-Frontend soll die Workflows aus dem akzeptierten statischen Prototyp schrittweise produktiv abbilden.

Bei UI-Arbeit:

- Bestehende Angular-/CoreUI-Muster beibehalten.
- Keine Marketing- oder Landingpage bauen; die App ist ein Arbeitswerkzeug.
- Dichte, klare, arbeitsorientierte Oberflaechen bevorzugen.
- Rollen, Status, Fehlermeldungen und leere Zustaende sichtbar und bedienbar machen.

## Tests und Qualitaet

Primaere lokale Gesamtpruefung ist:

```sh
mise run quality
```

Wenn nur ein Teilbereich geaendert wurde, gezielt passende Tests ausfuehren. Build- oder Testfehler nicht automatisch als Produktfehler werten, wenn sie eindeutig durch die lokale Sandbox verursacht sind; dann die Einschraenkung klar benennen.

### Codex-Sandbox

Die Codex-Sandbox ist nicht die massgebliche produktive Laufzeit. Einige lokale Vollpruefungen koennen dort wiederholt an bekannten Umgebungsgrenzen scheitern, obwohl sie in der normalen Entwicklungsumgebung oder in CI funktionieren.

Arbeite deshalb so:

- `mise run quality` bleibt die Referenz fuer vollstaendige lokale Qualitaetssicherung, soll in Codex aber nicht reflexhaft nach jeder Aenderung gestartet werden.
- Bei kleinen Aenderungen gezielt die betroffenen Tests oder Checks ausfuehren.
- Wenn ein bekannter Sandbox-Fehler erneut auftritt, nicht mehrfach denselben Vollcheck wiederholen und keine Produktfixes fuer reine Sandbox-Symptome einbauen.
- Wenn der Nutzer bestaetigt, dass ein Fehler sandbox-spezifisch ist, diese Einordnung uebernehmen und die verbleibenden echten Implementierungsluecken getrennt bewerten.
- Fuer vollstaendige Sicherheit CI oder eine Ausfuehrung ausserhalb der Codex-Sandbox heranziehen.
- Im Abschlussbericht klar unterscheiden zwischen `verifiziert`, `in Codex nicht verifizierbar` und `durch bekannte Sandbox-Grenze blockiert`.

Bekannte lokale Eigenheiten:

- `git status` kann durch `fsmonitor` stoeren; dann `git -c core.fsmonitor=false status ...` verwenden.
- Frontend-Builds oder Browser-/E2E-nahe Pruefungen koennen in der Codex-Sandbox anders scheitern als in der normalen Entwicklungsumgebung. Nach einem solchen bekannten Treffer nicht weiter am Produktcode drehen, sondern den Befund als Umgebungsthema dokumentieren.

## Entwicklungsumgebung

Die Toolchain ist im Repository festgelegt:

- Python ueber `uv`, `.python-version` und `.mise.toml`.
- Node/npm ueber `.node-version` und `.mise.toml`.
- VS-Code-Konfiguration liegt bewusst im Repository, soweit sie projektweit nuetzlich ist.

Wenn `node`, `npm`, `uv`, `mise` oder `gh` in Codex fehlen, zuerst PATH und lokale Installation pruefen, bevor Projektdateien angepasst werden.

## GitHub Project

Das GitHub Project heisst `lzug Roadmap`:

- URL: `https://github.com/users/lxndrp/projects/2`
- Board-Spalten sollten nach `Status` gruppiert sein.
- Filter nach `label:"type: epic"` und `label:"type: story"` sollen die fachliche Struktur sichtbar machen.

Zukuenftige operative Planung soll dort gepflegt werden. Repository-Dokumente bleiben ergaenzender Kontext und sollten bei grundlegenden fachlichen Entscheidungen aktualisiert werden.
