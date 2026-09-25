# Hinweise für Coding Agents

Diese Datei enthält die verbindlichen Projektregeln für Coding Agents.
Anleitungen für Menschen stehen im [GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung),
technische Details im [Entwicklerhandbuch](docs/developers/index.md).

## 1. Kanonischer Stand und Auftrag

- GitHub ist die kanonische Quelle für Aufgaben, Entscheidungen, Abhängigkeiten und Status.
Versionierter Code, technische Dokumentation und der reale Zustand externer Systeme bleiben für ihren jeweiligen Gegenstand maßgeblich.
Chat-Inhalte werden erst durch Dokumentation im passenden GitHub-Artefakt zum Projektstand.
- Das Issue enthält den vollständigen Umsetzungsauftrag: Ziel, Scope und Nicht-Scope, Akzeptanzkriterien, Entscheidungen, Abhängigkeiten, Blocker und betroffene Tests, Dokumentation, Pages, Wiki, Migration und Betrieb.
Das Project enthält Planungsmetadaten; Pull Request und CI belegen Umsetzung und Prüfung.
Inhalte nicht zwischen Artefakten duplizieren; Kommentare halten neue Entscheidungen, Befunde, Blocker oder Statusänderungen knapp fest.
- Vor Planung, Umsetzung und Statusauskunft aktuellen GitHub- und Git-Stand lesen.
Übergebene belastbare Startevidenz wiederverwenden; nur bei Lücke, Widerspruch oder relevanter Änderung gezielt aktualisieren.
- Ein Gedankenexperiment oder ein umsetzungsreifes Issue allein ist keine Beauftragung.
`Implementiere Issue #<nummer>.` ist bei umsetzungsreifem Issue ein vollständiger Auftrag bis zu Tests, Pull Request und geklärten Reviewbefunden im Scope.
Neue Entscheidungen oder Scope-Änderungen im Issue dokumentieren und genau einmal an die Koordination übergeben.

## 2. Verantwortlichkeiten und Delegation

| Rolle | Verantwortung |
| --- | --- |
| `Projekt entwickeln` | Interaktive Fachlichkeit, Architektur, Planung und Umgebung; bestätigte Ziele, Scope, Akzeptanzkriterien, Priority, Complexity, Schätzung, Iteration, Milestone und Project-README pflegen. |
| `Umsetzung koordinieren` | Reife einmal prüfen, ausdrücklich beauftragte Arbeit zuordnen, Ausführungsstatus pflegen und nach Freigabe Merge/Closeout einschließlich belegter Istwerte verantworten. |
| Verantwortlicher Bearbeiter je Issue | Code, Tests, Dokumentation, Pull Request, neue Reviewbefunde und Prüfnachweise im isolierten Arbeitsbereich liefern. |
| Review-Lauf | Geprüfte Revision und Abdeckung im Review-Anker dokumentieren und bestätigte Befunde nach Duplikatprüfung erfassen. |

- Planung, Refinement und Review bleiben gegenüber Produktcode read-only.
Die beiden dauerhaften Chats implementieren keine Produktänderungen in ihrem permanenten Arbeitsbereich.
Nicht triviale Repository-Änderungen zur Entwicklungsumgebung folgen ebenfalls dem Issue-Verfahren.
- Höchstens zwei Issue-Umsetzungen gleichzeitig, mit genau einem verantwortlichen Bearbeiter sowie eigenem Feature-Branch und Worktree je Issue.
Die Grenze zählt aktive Issue-Aufträge, nicht reine Recherche- oder Review-Teilaufträge; technische Agentenlimits gelten zusätzlich.
Abgegrenzte Arbeit kann ein Subagent übernehmen; längere oder interaktive Umsetzung erhält einen eigenständigen Issue-Task.
Die Koordination darf solche Tasks im ausdrücklich beauftragten Umfang anlegen.
Teilaufträge erhalten eindeutige Arbeitsbereiche; gleichzeitige Änderungen an denselben Dateien vermeiden.
- Der Branch heißt `codex/<issue>-<kurzer-name>`, ein eigenständiger Issue-Task `<issue> (<type>): <title>`.
Niemals direkt auf `master` committen; fremde Änderungen nicht zurücksetzen und nur auftragsbezogene Dateien stagen.
Bestehende Issue-Tasks laufen bei einer Prozessumstellung unverändert weiter.
- Übergaben enthalten den maßgeblichen Issue-/PR-Link und nur notwendige neue Angaben.
Keine Empfangsbestätigungs- oder Berichtsketten; der Stand bleibt an GitHub-Artefakten belegbar.
Ergebnisse delegierter Arbeit prüft der verantwortliche Bearbeiter vor Übernahme.
Unklare Zustellungen vor Wiederholung klären; laufende Tasks und Nutzerarbeit nicht stören.
- Reifeprüfung, Metadatenmutation und Closeout haben jeweils genau eine zuständige Stelle.
Eindeutige erfolgreiche Antworten genügen für reversible Routineoperationen; keine routinemäßige unabhängige Zweitprüfung.
Rückfragen auf unklare Entscheidungen, fehlende Berechtigungen, Blocker und begründete Modellhochstufungen beschränken.

Generische Verfahren liegen in persönlichen Skills: `lxndrp-github-project-planning`,
`lxndrp-github-delivery-coordination`, `lxndrp-github-issue-delivery` und `lxndrp-codebase-review`.
Roadmap-Review, Qualitäts-Triage, Review-Triage, Integration-Debugging und Umgebungsberatung ergänzen sie nach Bedarf.
Skills erteilen keine Befugnisse und ersetzen keine Projektregeln.
Fehlt ein Skill, das Verfahren anhand dieser Regeln und des Entwicklerhandbuchs durchführen;
fehlende Prüfungen oder Zugänge benennen, niemals Befugnisse oder Prüfergebnisse erfinden.
Der [Entwicklereinstieg](docs/developers/development.md) beschreibt Einrichtung und lokale Prüfungen.

## 3. Reife und Codebasis-Review

- Vor dem Start Issue, Kommentare, Labels, Milestone, Parent-/Sub-Issues, verknüpfte PRs, Abhängigkeiten, Blocker und erreichbare Project-Felder prüfen.
Die Koordination übergibt diese Startevidenz; ohne Übergabe prüft der verantwortliche Bearbeiter einmal selbst.
- Bei `needs:*`, fehlendem Ziel, Scope oder Akzeptanzkriterien, ungelösten Blockern, widersprüchlichen Angaben oder konkurrierender Umsetzung nicht beginnen.
Voraussetzungen nicht erfinden; konkreten Klärungsbedarf im GitHub-Artefakt dokumentieren.
- Vor der ersten regulären Umsetzung eines neuen SemVer-Milestones ist ein vollständiger Review des aktuellen `master` erforderlich.
Die Koordination veranlasst ihn und prüft den abgeschlossenen, dem Milestone zugeordneten Review-Anker.
Der Anker ist `type: task`, trägt selbst kein `review:*`-Label und dokumentiert feste Commit-SHA, Umfang, Abschluss und verknüpfte Befunde.
Ohne diesen Nachweis keine reguläre Umsetzung; reine Planung und Review sind selbst keine regulären Umsetzungen.
Für spätere Umsetzungen desselben Milestones genügt der vorhandene vollständige Nachweis, sofern kein neuer wesentlicher Befund einen weiteren Review erfordert.
- Der lokale Wochenreview folgt dem dokumentierten Verfahren für feste Revisionen und hält Umfang und Abschluss im Review-Anker fest.
Unvollständige Läufe verschieben den geprüften Ausgangsstand nicht; inkrementelle Nachweise ersetzen das vollständige Milestone-Gate nicht.
- Review-Befunde anhand von Evidenz bestätigen, gegen vorhandene Issues abgleichen und nur sachlich passende `review:*`-Labels verwenden.
Keine automatischen Reparaturen, Priorisierungen oder Planänderungen aus einem Review ableiten.
Benachrichtigungen auf neue relevante Befunde, Fehler und erforderliche Entscheidungen beschränken.

## 4. Umsetzung, Modelle und Prüfung

- `Complexity` wird live gelesen und steuert angemessene Prüfung, nicht automatisch Modell oder Reasoning.
Fehlende, unbekannte oder widersprüchliche Werte durch die Projektplanung klären; keine Einstufung erfinden.
Änderungen der Einstufung benötigen eine bestätigte Planungsentscheidung.
Bestehende C4-Zerlegungs- und menschliche Reviewregeln bleiben erhalten.
- Klar beschriebene Umsetzung startet mit Luna/medium.
Bei fachlicher Unsicherheit oder wiederholtem inhaltlichem Fehlversuch eine begründete Modell- oder Reasoning-Hochstufung beim Nutzer anfragen; nicht automatisch wechseln.
Sandboxfehler, Berechtigungen und CI-Wartezeit sind keine Modelleskalation.
- Die kleinste Änderung liefern, die das Issue vollständig erfüllt, einschließlich erforderlicher Tests, Dokumentation, Pages, Wiki, Migration und Betrieb.
Akzeptanzkriterien und beobachtbares Laufzeitverhalten belegen.
Werkzeugmigration, Wortlautprüfungen, Wrapper oder verschobener Code allein erfüllen keinen Vereinfachungsauftrag.
Bei Rückbau entfallene Eigenlogik und erhaltenes Verhalten dokumentieren.
- Commit-Nachrichten sind Englisch; deutsche Prosa verwendet korrekte Umlaute.
Eigene Markdown-Prosa verwendet Semantic Line Breaks; Tabellen, Listenstruktur, Codeblöcke, Front Matter, URLs und technische Zeichenketten unverändert lassen.
Drittmaterial, Lizenztexte und generierte Inhalte nicht rein redaktionell umbrechen.
- Lokal mindestens `git diff --check` und betroffene Format-, Link- oder Fachprüfungen ausführen.
Prüfungen und erforderliche Integrationsgrenzen am Änderungsrisiko ausrichten.
`task quality` ist für querschnittliche, Toolchain-, Abhängigkeits-, CI-, Migrations-, sicherheitsrelevante oder breite Backend-/Frontend-Änderungen vorgesehen.
Die vollständige finale Abnahme erfolgt in CI am exakten Kandidaten; ein Abschluss oder eine Übergabe verlangt keine zusätzliche vollständige lokale Wiederholung.
- Vollständige Quality-Evidenz nur nach dem dokumentierten Nachweisvertrag wiederverwenden; unvollständige oder fehlgeschlagene Runs sind kein Nachweis.
Zeitabhängige Vulnerability-, Secret- und externe Linkprüfungen folgen ihrer eigenen Frequenz.
- Sandbox-Probleme als Umgebungsthema von Produktfehlern trennen; unverändert fehlschlagende breite Prüfungen nicht wiederholen.

## 5. Pull Request, Freigaben und Closeout

- Vor `task pr:create` Assignees, Milestone und Project-Zuordnung einmal lesen und nur gesetzte Werte übergeben.
Vollständige Umsetzung erhält eine eigene Zeile `Closes #<nummer>`.
PR und Abschluss beschreiben knapp Ziel, Nachweis, Abweichung, relevante Befunde, wesentliche Modellabweichungen und belegte Goal-Metriken.
Keine Secrets, personenbezogenen Daten, Prompts oder internen Reasoning-Protokolle aufnehmen.
- Nach relevanten Änderungen betroffene lokale Prüfungen wiederholen sowie CI und Review des neuen Stands abwarten.
Review-Threads, allgemeine Kommentare, Security-Audits, Code-Scanning-Alerts und automatisierte PR-Hinweise vollständig prüfen.
Sinnvolle Befunde im Scope vor dem Auflösen beheben; unklare, unzutreffende oder sachfremde Hinweise beantworten oder eskalieren.
Übergaben und administrative Abgleiche ersetzen weder Code-/CI-Prüfungen noch erforderlichen menschlichen Review.
- Merge erst nach erfolgreicher CI des letzten Stands, geklärten relevanten Befunden und erfüllten Akzeptanzkriterien.
Merge, Release, Workflow-Dispatch und externe Aktivierung benötigen ausdrückliche Maintainer-Freigabe.
Den freigegebenen Merge führt die Koordination aus, nicht der Umsetzungsbearbeiter.
Azure-, DNS-, GitHub-Environment-, Secret-, OIDC-, Deployment- und OpenTofu-`apply`-Änderungen ebenfalls nur nach ausdrücklicher Freigabe; externe Systeme zunächst read-only prüfen.
- Qualifizierte Dependabot-PRs nur durch den vorgesehenen Squash-Auto-Merge-Workflow anmelden.
Major-, GitHub-Actions-, konfliktäre oder nicht eindeutig klassifizierte Updates bleiben manuell.
- Fortschritt und Abschluss im Issue dokumentieren.
Je Issue ein eigenes Codex-Goal verwenden, soweit technisch isoliert zurechenbar; erst nach erreichtem Ziel und lokaler Prüfung abschließen.
Kein Tokenbudget erfinden.
Die Koordination übernimmt ausschließlich ausgewiesene finale Laufzeit als Stunden in `Factual effort (h)` und Tokenzahl unverändert in `Cost (Tokens)`.
Fehlende Einzelwerte bleiben leer; gemeinsame Eltern-/Subagent-Metriken nicht verteilen und historische Werte nicht schätzen.
- Nach freigegebenem Merge, finaler CI und geklärten Reviews entfernt die Koordination nur den zugehörigen sauberen Worktree und lokalen/Remote-Feature-Branch.
Zuvor auch lokale und ignorierte Daten prüfen.
Der Worktree darf ohne Rückfrage entfernt werden, wenn der Merge-Commit auf `origin/master` liegt,
keine nicht ignorierten oder auftragsfremden Änderungen vorhanden sind und nur eindeutig regenerierbare Standardartefakte verbleiben,
etwa virtuelle Python-Umgebungen, Bytecode-, Test- oder Linter-Caches sowie vergleichbare werkzeuggenerierte Build-Caches.
Alle sonstigen ignorierten oder nicht eindeutig zuordenbaren Artefakte benennt die Koordination
und verwirft oder sichert sie nur nach ausdrücklicher Entscheidung.
Eigenständige Umsetzungstasks nicht automatisch archivieren.
- Bei Statusaufträgen aktuellen Stand von Issue, Akzeptanzkriterien, PR, Reviews, CI, Dokumentation, Pages/Wiki, Branch und Worktree prüfen.
Am Iterationsende und vor Release-Abschluss offene PR-/CI-/Closeout-Reste, verwaiste Arbeitsbereiche sowie Project-Zuordnung, Status und vorhandene Istwerte einmal gebündelt abgleichen.
Dieser ereignisgesteuerte Closeout ist vom wöchentlichen Codebasis-Review getrennt.
Die Koordination korrigiert belegte Ausführungsdaten; erforderliche Planänderungen gehen einmal an `Projekt entwickeln` und benötigen eine bestätigte Entscheidung.

Ergänzend gelten die Frontend- und Reviewregeln unter
[Komponenten](docs/developers/components.md) und [Entwicklung](docs/developers/development.md).
