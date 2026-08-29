# Hinweise für Coding Agents

Diese Datei enthält die verbindlichen Regeln für Codex und andere Coding Agents
in diesem Repository. Anleitungen für Menschen stehen im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung), technische
Details im [Entwicklerhandbuch](docs/developers/index.md).

## 1. Kanonischer Stand

- GitHub ist die kanonische Quelle für Aufgaben, Entscheidungen, Abhängigkeiten
und Status.
Der versionierte Code und die technische Dokumentation im Repository sowie der reale Zustand externer Systeme bleiben jeweils für ihren Gegenstand maßgeblich.
Chat-Inhalte werden erst durch Dokumentation im passenden GitHub-Artefakt zum Projektstand.
- Das Issue ist der vollständige Umsetzungsauftrag: Ziel, Scope und Nicht-Scope,
Akzeptanzkriterien, Entscheidungen, Abhängigkeiten und Blocker sowie betroffene Tests, Dokumentation, Pages, Wiki, Migration und Betrieb.
- Das GitHub Project enthält Planungsmetadaten. Pull Request und CI belegen
Umsetzung und Prüfung.
Repository, Pages und Wiki enthalten die dauerhafte Dokumentation.
- Inhalte nicht zwischen Artefakten oder Chats duplizieren. Issue- und
Pull-Request-Beschreibungen sowie Kommentare bleiben kurz und zweckbezogen; Kommentare halten nur neue Entscheidungen, Befunde, Blocker oder Statusänderungen fest.
- Vor Planung, Umsetzung und Statusauskunft den aktuellen GitHub- und Git-Stand
lesen.
Frühere Chat-Inhalte sind kein Ersatz dafür.

## 2. Arbeitskontexte

- Planung, Refinement und Review bleiben gegenüber dem Produktcode read-only.
- Die Cloud-Chats `Fachlichkeit strukturieren`, `Projektablauf planen` und
`Codebasis reviewen` dienen ausschließlich der fachlichen Strukturierung, Projektplanung und Codebasisbewertung.
Sie ändern weder Produktcode noch lokale Repository-Dateien, Branches oder Worktrees.
- `Fachlichkeit strukturieren` darf Ergebnisse fachlicher Klärungen in GitHub
Issues dokumentieren sowie bestehende Issues fachlich refinen.
Technische Umsetzungen und Produktcode bleiben ausgeschlossen.
- `Projektplan aktualisieren` überführt bestätigte Planungsentscheidungen aus
den Cloud-Chats lokal mittels `gh` in GitHub Project, Issues, Abhängigkeiten und Unteraufgaben.
Der Chat ändert keine Repository-Dateien, Branches oder Worktrees.
- `Weiterentwicklung koordinieren` prüft die Umsetzungsreife, startet und
überwacht issuebezogene Umsetzungen und führt deren Closeout aus.
Der Chat implementiert nicht in seinem eigenen Arbeitsbereich.
- `Entwicklungsumgebung anpassen` pflegt die lokale Entwicklungsumgebung. Nicht
triviale Repository-Änderungen folgen ebenfalls dem Issue-Verfahren.
- Externe Systeme zunächst read-only prüfen. Azure-, DNS-, GitHub-Environment-,
Secret-, OIDC-, Deployment- und OpenTofu-`apply`-Änderungen erfolgen nur nach ausdrücklicher Freigabe des Maintainers.
- Die sechs permanenten Chats `Fachlichkeit strukturieren`, `Projektablauf
planen`, `Codebasis reviewen`, `Weiterentwicklung koordinieren`, `Projektplan aktualisieren` und `Entwicklungsumgebung anpassen` weder umbenennen noch für eine Umsetzung verwenden oder archivieren.

## 3. Umsetzungsreife und Arbeitsbereich

- `Implementiere Issue #<nummer>.` ist ein vollständiger Auftrag, wenn das Issue
umsetzungsreif ist.
Das Issue bleibt maßgeblich; eine Übergabe ergänzt nur noch nicht dort dokumentierte, entscheidungsrelevante Randbedingungen.
- Vor Beginn Issue, Kommentare, verknüpfte Pull Requests, Abhängigkeiten,
Blocker und erreichbare Project-Felder prüfen.
- Nicht beginnen, solange das Issue ein `needs:*`-Label trägt. Dasselbe gilt bei
fehlendem Ziel, Scope oder Akzeptanzkriterien, ungelösten Blockern, widersprüchlichen Angaben oder einer konkurrierenden Umsetzung.
- Voraussetzungen nicht erfinden. Bei fehlender Reife stoppen und den konkreten
Klärungsbedarf im vorgesehenen GitHub-Artefakt dokumentieren.
- Für nicht triviale Änderungen gilt: ein Issue entspricht genau einem
temporären Umsetzungschat, einem Feature-Branch und einem Worktree.
- Einen Umsetzungschat unabhängig neu anlegen, nicht durch Umbenennen,
Delegation oder Übergabe eines permanenten Chats.
- Den Arbeitsbereich mit dem vorgesehenen lokalen Skill anlegen und aufräumen,
soweit verfügbar.
Der Umsetzungschat heißt `<issue> (<type>): <title>`, der Branch `codex/<issue>-<kurzer-name>`.
- Der Umsetzungschat bezieht seinen Auftrag unmittelbar aus GitHub. Übergaben
dürfen das Issue weder ersetzen noch abweichend erweitern.

## 4. Umsetzung und Prüfung

- Ausschließlich im issuebezogenen Worktree arbeiten und niemals direkt auf
`master` committen.
Fremde oder ungefragte Änderungen nicht zurücksetzen und nur auftragsbezogene Dateien stagen.
- Die kleinste Änderung umsetzen, die das Issue vollständig erfüllt. Nicht zum
Scope gehörende Refactorings vermeiden.
Geforderte Tests, Dokumentation, Pages-, Wiki-, Migrations- und Betriebsänderungen gehören zur Umsetzung.
- Commit-Nachrichten sind Englisch; deutsche Prosa verwendet korrekte Umlaute.
- Eigene gepflegte Markdown-Prosa wird mit Semantic Line Breaks geschrieben:
Sätze und sinnvolle Gedankeneinheiten beginnen in neuen Quellzeilen.
Tabellen, Listenstruktur, Codeblöcke, Front Matter, URLs und technische Zeichenketten bleiben unverändert; Drittmaterial, Lizenztexte und generierte Inhalte werden nicht rein redaktionell umgebrochen.
- Prüfungen am Änderungsrisiko ausrichten. Eng begrenzte Änderungen erhalten
mindestens `git diff --check` und die betroffenen Format-, Link- oder Fachprüfungen.
- `task quality` ist für querschnittliche, Toolchain-, Abhängigkeits-, CI-,
Migrations-, sicherheitsrelevante oder breite Backend-/Frontend-Änderungen vorgesehen.
Die finale Abnahme bleibt der CI vorbehalten.
- Sandbox-Probleme als Umgebungsthema dokumentieren und von Produktfehlern
trennen.
Unverändert fehlschlagende breite Prüfungen nicht wiederholen.

## 5. Pull Request und Review

- Vor dem Pull Request Assignees, Milestone und Project-Zuordnung mit
`gh issue view` prüfen und mit `task pr:create` übernehmen; nicht gesetzte Felder bleiben leer.
- Vollständige Umsetzungen enthalten eine eigene Zeile `Closes #<nummer>`.
Danach Zuordnungen und schließende Verknüpfung mit `gh pr view` prüfen.
- Nach relevanten Änderungen die betroffenen lokalen Prüfungen wiederholen und
CI sowie Review erneut abwarten.
Review-Threads, allgemeine Kommentare, Security-Audits, Code-Scanning-Alerts und automatisierte Prüfhinweise mit Pull-Request-Bezug vollständig prüfen.
- Sinnvolle Hinweise im Issue-Scope umsetzen. Threads erst danach als
`Resolved` markieren.
Unklare, unzutreffende oder sachfremde Hinweise beantworten oder eskalieren.
- Erst mergen, wenn die CI nach den letzten Änderungen erfolgreich ist, alle
relevanten Befunde geklärt und die Akzeptanzkriterien erfüllt sind.
- Merge, Release, Workflow-Dispatch und externe Aktivierung erfolgen nur nach
ausdrücklicher Freigabe des Maintainers.
- Qualifizierte Dependabot-Pull-Requests werden nur durch den vorgesehenen
Squash-Auto-Merge-Workflow angemeldet.
Major-, GitHub-Actions-, konfliktäre oder nicht eindeutig klassifizierte Updates bleiben manuell.

## 6. Statusprüfung und Closeout

- Fortschritt und Abschluss im zugehörigen Issue kurz dokumentieren.
- Bei `Prüfe den Stand von Issue #<nummer>.` den Live-Stand von Issue,
Akzeptanzkriterien, Pull Request, Reviews, CI, Dokumentation, Pages/Wiki sowie Branch und Worktree prüfen; nicht aus dem Chatverlauf auf den Status schließen.
- Erst nach vollständiger Umsetzung, Merge, finaler CI und geklärten Reviews
abschließen.
Den Worktree zuvor auf lokale Reständerungen prüfen.
- Bei Reständerungen stoppen, die Dateien benennen und erst nach ausdrücklicher
Entscheidung sichern oder verwerfen.
Ist der Worktree sauber, ausschließlich den zugehörigen Worktree sowie lokalen und Remote-Feature-Branch entfernen und den temporären Umsetzungschat nicht archivieren; dessen Archivierung erfolgt manuell durch den Maintainer.

## 7. Codex-Sandbox

- Vor Browserprüfungen `task doctor` verwenden. Den gemeinsamen uv-Cache unter
`~/.cache/uv` nur über die globale Codex-Konfiguration freigeben; keine benutzerspezifische Konfiguration versionieren.
- Browser-E2E- und A11y-Prüfungen getrennt halten. Nicht reproduzierbare
Browserfehler gezielt lokal freigeben oder durch CI abnehmen lassen.
Chromium nie mit `--no-sandbox` starten.
- Bei störendem Git-Fsmonitor
`git -c core.fsmonitor=false status ...` verwenden.

Ergänzend gelten die [Frontend-Richtlinie](docs/developers/frontend-guidelines.md), die kanonische [Review Policy](docs/developers/reviews/index.md) und das [Entwicklerhandbuch](docs/developers/index.md).
