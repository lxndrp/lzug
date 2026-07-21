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
- Fehler als echte GitHub Issues mit Label `type: bug`.
- Epics und Stories ueber Parent/Sub-Issues verknuepfen.
- Das GitHub Project `lzug Roadmap` fuer Status, Board-Ansicht und Priorisierung nutzen.

Draft-Items im GitHub Project nur fuer sehr fruehe Ideen verwenden. Sobald ein Element handhabbar oder nachvollziehbar sein soll, als Issue anlegen.

### Issues aus dem Chat

Neue fachliche oder technische Vorhaben koennen direkt im Chat gemeldet werden,
wenn die Nachricht mit einem der folgenden Praefixe beginnt:

- `Story: <Titel>`: GitHub Issue mit Label `type: story` anlegen.
- `Epic: <Titel>`: GitHub Issue mit Label `type: epic` anlegen.
- `Bug: <Titel>`: GitHub Issue mit Label `type: bug` anlegen.

Den restlichen Text der Meldung als Issue-Titel verwenden und die verfuegbaren
Details als Issue-Beschreibung uebernehmen. Das Issue dem GitHub Project
`lzug Roadmap` hinzufuegen und grundsaetzlich auf `Todo` setzen. Wenn aus dem
Kontext ein Parent-Epic oder eine weitere Verknuepfung erkennbar ist, diese
ebenfalls anlegen. Bei unzureichenden Angaben die fehlenden Details im Chat
klaeren, bevor eine umfangreiche Umsetzung beginnt.

### Refinements

- Refinements von Stories und Epics werden durch eine Aktualisierung des Issue-
  Titels, der Beschreibung, der Labels oder der Verknuepfungen abgebildet.
- Refinements von Bugs werden als zusaetzlicher Kommentar im bestehenden Bug-
  Issue dokumentiert. Die urspruengliche Fehlerbeschreibung bleibt erhalten.
- Nach einem Refinement den Project-Status nur aendern, wenn sich daraus ein
  tatsaechlicher Fortschritt oder eine neue Priorisierung ergibt.

### Trennung von Planung und Umsetzung

- Planung, Refinement und fachliche Klaerung finden im jeweiligen
  Planungsthread statt.
- Threads zu einem GitHub Issue werden nach dem Muster
  `<issue> (<type>): <title>` benannt. Dabei bezeichnet `<issue>` die
  Issue-Nummer, `<type>` das relevante Type-Label ohne den Praefix `type:`
  beziehungsweise `bug` fuer Bug-Issues und `<title>` den Issue-Titel.
- Diese Namensstruktur gilt fuer Planungs- und Umsetzungsthreads; eine
  zusaetzliche Unterscheidung nach Feature oder Bug ist nicht erforderlich.
- Jeder Umsetzungsthread fuer ein Issue erhaelt einen eigenen Worktree. Der
  Worktree wird mit dem zugehoerigen Feature-Branch verbunden und darf nicht
  parallel mit dem Planungsthread im selben Arbeitsverzeichnis arbeiten.
- Beim Wechsel von der Planung in die Umsetzung den fuer die Implementierung
  relevanten Kontext an den passenden Umsetzungsthread uebergeben. Dazu gehoeren
  mindestens Issue-Nummer, fachliches Ziel, Akzeptanzkriterien, technische
  Entscheidungen, bekannte Randbedingungen und offene Punkte.
- Im Planungsthread keine umfangreiche Implementierung beginnen, sobald ein
  passender Umsetzungsthread vorgesehen oder bereits vorhanden ist.

## Statusmodell

Im GitHub Project gelten die Standardstatus:

- `Todo`: aufgenommen, noch nicht begonnen.
- `In Progress`: aktuell in Arbeit oder aktives Epic.
- `Done`: abgeschlossen und nachvollziehbar dokumentiert.

Geschlossene Issues nicht loeschen.

### Issue-Labels

- Jedes manuell angelegte Issue erhaelt genau ein `type:`-Label: `epic`,
  `story`, `task` oder `bug`.
- `resolution:`-Labels dokumentieren die abschliessende Einordnung eines Issues
  und sind optional: `duplicate`, `invalid`, `wontfix` oder `help-wanted`.
- `type:` beschreibt die Art des Arbeitselements; `resolution:` beschreibt,
  warum ein Issue nicht weiterverfolgt oder wie es abgeschlossen wurde.
- Die Dependabot-Labels `dependencies` und `github_actions` sind technische
  Automationslabels und koennen zusaetzlich verwendet werden.

## Git und Commits

- Produkt- und Fehlerbehebungsarbeiten, die zu einer Story, einem Epic oder
  einem Bug-Issue gehoeren, immer in einem eigenen Feature-Branch umsetzen.
- Branches fuer Codex-Arbeiten nach dem Muster
  `codex/<issue>-<kurzer-name>` benennen, unabhaengig vom Type-Label.
- Niemals direkt in `master` committen, wenn die Aenderung ein Issue umsetzt.
- Nach der Verifikation einen Pull Request gegen `master` eroeffnen und das
  umgesetzte Issue im Pull Request verknuepfen. Fuer vollstaendig umgesetzte
  Issues `Closes #<nummer>` verwenden; bei Teilumsetzungen eine nicht
  schliessende Verknuepfung wie `Related to #<nummer>` nutzen.
- Den Pull Request erst nach erfolgreicher CI und Review in `master` mergen.
- Nach dem Merge den Issue-Status im GitHub Project auf `Done` setzen und das
  Issue schliessen, sofern die Umsetzung vollstaendig ist.
- Nach erfolgreichem Merge aller zugehoerigen Pull Requests, erfolgreicher CI
  und abgeschlossenem Review den zugehoerigen Planungsthread beziehungsweise
  Umsetzungsthread archivieren. Danach den Issue-Worktree entfernen, den
  lokalen Feature-Branch loeschen und den zugehoerigen Remote-Branch in
  GitHub loeschen. Nur die dem abgeschlossenen Issue zugeordneten Worktrees
  und Branches aufraeumen; `master`, andere Issues und aktive Arbeitsverzeichnisse
  nicht loeschen.
- Aenderungen thematisch schneiden und kleine, nachvollziehbare Commits bevorzugen.
- Commit-Messages bevorzugt auf Englisch schreiben, passend zur bisherigen Git-Historie.
- Deutsch und Englisch nicht innerhalb einer Commit-Message mischen.
- Vor Commits `git -c core.fsmonitor=false status ...` verwenden, wenn `fsmonitor` lokal stoert.
- Nur Dateien stagen, die zum aktuellen Arbeitsauftrag gehoeren.

## Tests und Verifikation

Die lokale Qualitaetssicherung ist der erste Pruefschritt fuer jede Aenderung.

- Massgeblich ist grundsaetzlich `mise quality`.
- Bei klar eingegrenzten Aenderungen duerfen zunaechst passende Teiltests oder
  Checks ausgefuehrt werden.
- Wenn ein Teilcheck erfolgreich ist, aber die Aenderung weitere Bereiche
  beruehrt oder die Ursache nicht vollstaendig eingegrenzt ist, folgt
  `mise quality`.
- GitHub Actions wird erst gestartet, wenn die lokale Qualitaetssicherung
  erfolgreich durchlaufen wurde.
- Die GitHub-Actions-Pipeline ist anschliessend die finale Verifikation und
  massgeblich fuer die Abnahme.
- Wenn lokale Pruefungen in Codex durch eine bekannte Sandbox-Grenze blockiert
  sind, ist die Aenderung nicht lokal verifiziert. In diesem Fall wird nicht
  automatisch GitHub Actions als Ersatz gestartet; der Befund wird als
  Umgebungsproblem dokumentiert.

Im Abschlussbericht klar unterscheiden zwischen:

```sh
mise quality
```

- `verifiziert`
- `in Codex nicht verifizierbar`
- `durch bekannte Sandbox-Grenze blockiert`

Bei neuen fachlichen Aenderungen sollen Tests schichtweise ergaenzt werden:

1. Domain-/Repository-Regeln und Statusuebergaenge im Backend.
2. HTTP- und OpenAPI-Vertrag inklusive Fehlerantworten.
3. Frontend-Komponenten und API-Service mit isolierten Fixtures.
4. Mindestens ein Browser-Szenario fuer den fachlichen End-to-End-Nutzen.

## Continuous Integration

Die vollstaendige Projektpruefung laeuft in `.github/workflows/ci.yml` auf Pushes und Pull Requests gegen `main` und `master`. Sie wird erst nach erfolgreicher lokaler Qualitaetssicherung gestartet und ist anschliessend die finale Verifikation fuer die Abnahme.

Dependency- und Security-Hinweise sind getrennt vom CI-Aufbau zu bewerten und blockieren den Workflow nicht automatisch.

## Codex-Sandbox

Die Codex-Sandbox ist nicht die massgebliche produktive Laufzeit. Einige lokale Vollpruefungen koennen dort wiederholt an bekannten Umgebungsgrenzen scheitern, obwohl sie in der normalen Entwicklungsumgebung oder in CI funktionieren.

Arbeite deshalb so:

- Bei kleinen, klar eingegrenzten Aenderungen gezielt die betroffenen Tests oder Checks ausfuehren und anschliessend bei Bedarf `mise quality` starten.
- Wenn ein bekannter Sandbox-Fehler erneut auftritt, nicht mehrfach denselben Vollcheck wiederholen.
- Keine Produktfixes fuer reine Sandbox-Symptome einbauen.
- Wenn der Nutzer bestaetigt, dass ein Fehler sandbox-spezifisch ist, diese Einordnung uebernehmen und die verbleibenden echten Implementierungsluecken getrennt bewerten.
- Fuer die finale Abnahme nach erfolgreicher lokaler QA GitHub Actions heranziehen; wenn die lokale QA durch eine bekannte Sandbox-Grenze blockiert ist, den Befund als nicht lokal verifiziert dokumentieren.

Bekannte lokale Eigenheiten:

- `git status` kann durch `fsmonitor` stoeren; dann `git -c core.fsmonitor=false status ...` verwenden.
- Frontend-Builds oder Browser-/E2E-nahe Pruefungen koennen in der Codex-Sandbox anders scheitern als in der normalen Entwicklungsumgebung. Nach einem solchen bekannten Treffer nicht weiter am Produktcode drehen, sondern den Befund als Umgebungsthema dokumentieren.

## Fuehrende Dokumente

- `README.md`: Produktueberblick, fachliche Hauptbereiche, Setup und zentrale Einstiegspunkte.
- `docs/ARCHITECTURE.md`: technische Architektur, Technologieentscheidungen, Backend-/Frontend-Schichtung, API, Datenbank und CI.
- `ROADMAP.md`: fachlicher Referenzstand, umgesetzte und offene Anforderungen, Epics und Plan.
- GitHub Project `lzug Roadmap`: operative Planung und Statusverfolgung.
