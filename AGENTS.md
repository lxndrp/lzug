# lzug Agent Instructions

Diese Datei beschreibt, wie Codex und andere Coding Agents in diesem Repository arbeiten sollen. Produktbeschreibung, fachlicher Umfang, Architektur und Technologieauswahl gehoeren in `README.md` und `ROADMAP.md`, nicht in diese Datei.

## Grundsatz

- Vor groesseren Aenderungen den aktuellen Repository-Zustand lesen statt aus Erinnerung zu arbeiten.
- Bestehende Git-Historie, Artefakte und nicht selbst vorgenommene Aenderungen bewahren.
- Keine fremden oder ungefragten Aenderungen zuruecksetzen.
- Wenn der Nutzer Planung statt Umsetzung verlangt, read-only bleiben.
- Wenn der Nutzer Umsetzung verlangt, die Arbeit bis zur angemessenen Verifikation durchziehen.

## Planung und Nachverfolgung

Arbeite nach diesem Modell:

- Chat und lokale Notizen sind Arbeitsgedaechtnis.
- Repository-Dokumente sind versionierter Kontext fuer Produkt, Architektur und Entscheidungen.
- GitHub Issues und GitHub Projects sind die dauerhafte Quelle fuer Backlog, Fortschritt und Nachverfolgung.

Wenn fachliche oder technische Planung in Codex entsteht und belastbar genug ist, ueberfuehre sie in GitHub:

- Epics als echte GitHub Issues mit Label `type: epic`.
- User Stories als echte GitHub Issues mit Label `type: story`.
- Technische Aufgaben als echte GitHub Issues mit Label `type: task`.
- Nachtraeglich importierte Bestands- oder Entscheidungsdokumentation mit Label `source: baseline-import`.
- Epics und Stories ueber Parent/Sub-Issues verknuepfen.
- Das GitHub Project `lzug Roadmap` fuer Status, Board-Ansicht und Priorisierung nutzen.

Draft-Items im GitHub Project nur fuer sehr fruehe Ideen verwenden. Sobald ein Element handhabbar oder nachvollziehbar sein soll, als Issue anlegen.

## Statusmodell

Im GitHub Project gelten die Standardstatus:

- `Todo`: aufgenommen, noch nicht begonnen.
- `In Progress`: aktuell in Arbeit oder aktives Epic.
- `Done`: abgeschlossen und nachvollziehbar dokumentiert.

Geschlossene Issues nicht loeschen. Wenn sie aus einer nachtraeglichen Ueberfuehrung stammen, muessen sie transparent als Baseline-Import markiert sein.

## Git und Commits

- Aenderungen thematisch schneiden und kleine, nachvollziehbare Commits bevorzugen.
- Commit-Messages bevorzugt auf Englisch schreiben, passend zur bisherigen Git-Historie.
- Deutsch und Englisch nicht innerhalb einer Commit-Message mischen.
- Vor Commits `git -c core.fsmonitor=false status ...` verwenden, wenn `fsmonitor` lokal stoert.
- Nur Dateien stagen, die zum aktuellen Arbeitsauftrag gehoeren.

## Tests und Verifikation

Primaere lokale Gesamtpruefung ist:

```sh
mise run quality
```

Wenn nur ein Teilbereich geaendert wurde, gezielt passende Tests oder Checks ausfuehren. Im Abschlussbericht klar unterscheiden zwischen:

- `verifiziert`
- `in Codex nicht verifizierbar`
- `durch bekannte Sandbox-Grenze blockiert`

Bei neuen fachlichen Aenderungen sollen Tests schichtweise ergaenzt werden:

1. Domain-/Repository-Regeln und Statusuebergaenge im Backend.
2. HTTP- und OpenAPI-Vertrag inklusive Fehlerantworten.
3. Frontend-Komponenten und API-Service mit isolierten Fixtures.
4. Mindestens ein Browser-Szenario fuer den fachlichen End-to-End-Nutzen.

## Continuous Integration

Die vollstaendige Projektpruefung laeuft in `.github/workflows/ci.yml` auf Pushes und Pull Requests gegen `main` und `master`.

Fuer die vollstaendige Verifikation sind erfolgreiche Jobs in GitHub Actions massgeblich, wenn lokale Pruefungen an der Codex-Sandbox scheitern. Dependency- und Security-Hinweise sind getrennt vom CI-Aufbau zu bewerten und blockieren den Workflow nicht automatisch.

## Codex-Sandbox

Die Codex-Sandbox ist nicht die massgebliche produktive Laufzeit. Einige lokale Vollpruefungen koennen dort wiederholt an bekannten Umgebungsgrenzen scheitern, obwohl sie in der normalen Entwicklungsumgebung oder in CI funktionieren.

Arbeite deshalb so:

- `mise run quality` bleibt die Referenz fuer vollstaendige lokale Qualitaetssicherung, soll in Codex aber nicht reflexhaft nach jeder Aenderung gestartet werden.
- Bei kleinen Aenderungen gezielt die betroffenen Tests oder Checks ausfuehren.
- Wenn ein bekannter Sandbox-Fehler erneut auftritt, nicht mehrfach denselben Vollcheck wiederholen.
- Keine Produktfixes fuer reine Sandbox-Symptome einbauen.
- Wenn der Nutzer bestaetigt, dass ein Fehler sandbox-spezifisch ist, diese Einordnung uebernehmen und die verbleibenden echten Implementierungsluecken getrennt bewerten.
- Fuer vollstaendige Sicherheit CI oder eine Ausfuehrung ausserhalb der Codex-Sandbox heranziehen.

Bekannte lokale Eigenheiten:

- `git status` kann durch `fsmonitor` stoeren; dann `git -c core.fsmonitor=false status ...` verwenden.
- Frontend-Builds oder Browser-/E2E-nahe Pruefungen koennen in der Codex-Sandbox anders scheitern als in der normalen Entwicklungsumgebung. Nach einem solchen bekannten Treffer nicht weiter am Produktcode drehen, sondern den Befund als Umgebungsthema dokumentieren.

## Fuehrende Dokumente

- `README.md`: Produktueberblick, fachliche Hauptbereiche, Setup und zentrale Einstiegspunkte.
- `docs/ARCHITECTURE.md`: technische Architektur, Technologieentscheidungen, Backend-/Frontend-Schichtung, API, Datenbank und CI.
- `ROADMAP.md`: fachlicher Referenzstand, umgesetzte und offene Anforderungen, Epics und Plan.
- GitHub Project `lzug Roadmap`: operative Planung und Statusverfolgung.
