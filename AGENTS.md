# Hinweise für Coding Agents

Diese Datei enthält ausschließlich Regeln für Codex und andere Coding Agents.
Die Anleitungen für menschliche Beiträge stehen im
[Entwicklungsbereich des GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung),
die technische Referenz im [Entwicklerhandbuch](docs/developers/index.md).

## Arbeitsweise

- Vor Änderungen den aktuellen Repository- und Git-Status lesen; fremde oder
  ungefragte Änderungen niemals zurücksetzen.
- Bei Planung, Refinement oder fachlicher Klärung read-only bleiben. Umfangreiche
  Umsetzung erst im zugehörigen Issue-Worktree beginnen.
- Nur Dateien stagen, die zum Auftrag gehören. Commit-Nachrichten sind Englisch;
  deutsche Prosa verwendet korrekte Umlaute.
- Vor einer Umsetzung das Risiko der Änderung einschätzen und die lokalen
  Prüfungen darauf begrenzen: Eng begrenzte Änderungen erhalten mindestens
  `git diff --check` sowie die betroffenen Format-, Link- oder Fachprüfungen.
  Die Auswahl richtet sich nach Änderungsrisiko und betroffenen
  Schnittstellen, nicht allein nach Dateitypen. `task quality` ist für
  querschnittliche, Toolchain-, Abhängigkeits-, CI-, Datenbankmigrations-,
  sicherheitsrelevante oder breit angelegte Backend-/Frontend-Änderungen
  vorgesehen. Die vollständige finale Abnahme bleibt der CI vorbehalten.
  Bekannte Sandbox-Fehler als Umgebungsthema dokumentieren und breite
  Prüfungen deswegen nicht mehrfach unverändert wiederholen.

## Threads und Worktrees

- Die permanenten Planungsthreads `Fachlichkeit strukturieren`,
  `Entwicklungsumgebung anpassen` und `Weiterentwicklung planen` bleiben
  dauerhaft erhalten. Sie dürfen weder umbenannt noch archiviert oder für eine
  Umsetzung verwendet werden.
- Der Thread `Fachlichkeit strukturieren` darf die Ergebnisse fachlicher
  Klärungen in GitHub Issues dokumentieren, bestehende Issues refinen und ihre
  fachliche Einordnung pflegen. Er erstellt oder ändert dabei weder Produktcode
  noch technische Umsetzungen.
- Planung und Umsetzung eines Issues in getrennten Threads durchführen. Vor
  Beginn der Umsetzung muss die Bezeichnung des Umsetzungsthreads
  `<issue> (<type>): <title>` entsprechen; andernfalls ist sie zuerst zu
  korrigieren.
- Einen Umsetzungsthread als unabhängigen neuen Task anlegen, nicht durch
  Umbenennen, Delegation oder Übergabe eines permanenten Planungsthreads.
- Beim Wechsel in die Umsetzung Issue-Nummer, Ziel, Akzeptanzkriterien,
  technische Entscheidungen, Randbedingungen und offene Punkte vollständig an
  den Umsetzungsthread übergeben.
- Jeder Umsetzungsthread arbeitet ausschließlich in einem eigenen Worktree auf
  einem Feature-Branch `codex/<issue>-<kurzer-name>`; niemals direkt auf
  `master` committen.
- Fortschritt und Abschluss im zugehörigen Issue kommentieren. Vor dem Pull
  Request Assignees, Milestone und Project-Zuordnung des Issues mit `gh issue
  view` prüfen und mit `task pr:create` explizit übernehmen; nicht gesetzte
  Issue-Felder bleiben leer. Vollständige Umsetzungen enthalten eine eigene
  Zeile `Closes #<nummer>`. Nach dem Anlegen Project, Milestone, Assignees und
  schließende Issue-Verknüpfung mit `gh pr view` prüfen. Anschließend den
  Abschluss von CI und Code-Review abwarten und alle
  Kommentare und Befunde mit Pull-Request-Bezug prüfen. Dazu zählen
  Review-Threads, allgemeine Pull-Request-Kommentare, Security-Audits,
  Code-Scanning-Alerts und automatisierte Prüfhinweise. Sinnvolle, zum Issue
  gehörende Hinweise umsetzen und danach die betroffenen Prüfungen sowie CI
  erneut abwarten. Erledigte Review-Threads erst nach Prüfung beziehungsweise
  Umsetzung als `Resolved` markieren. Unklare, nicht sinnvolle oder außerhalb
  des Issue-Scopes liegende Hinweise nicht stillschweigend auflösen, sondern
  nachvollziehbar beantworten oder zur Entscheidung eskalieren. Erst mergen,
  wenn die CI nach den letzten Änderungen erfolgreich ist und alle relevanten
  Kommentare und Befunde geklärt sind.
- Copilot-Code-Reviews sind eine optionale, bewusst manuell angeforderte
  Zusatzperspektive und kein Merge-Gate. Bei Änderungen an Authentifizierung,
  Autorisierung, Sitzungen, Kryptographie, Datenmigrationen, Persistenz- oder
  Löschinvarianten, öffentlichen API-Verträgen, Cross-Stack-Abläufen,
  GitHub-Actions, Release- oder Container-Konfiguration sowie bei größeren
  schwer überblickbaren Änderungen den Maintainer darauf hinweisen. Die
  Entscheidung liegt beim Maintainer; eine nicht angeforderte oder ausgebliebene
  Copilot-Review blockiert den Fortschritt nicht.
- Qualifizierte Dependabot-PRs werden nur durch den dafür vorgesehenen Workflow
  für Squash-Auto-Merge angemeldet. Das bestehende Ruleset und die CI bleiben
  maßgeblich; Major-, GitHub-Actions-, konfliktbehaftete und nicht eindeutig
  klassifizierte Updates bleiben manuell.
- Der Merge-Closeout erfolgt nach Merge, erfolgreicher CI und Review im selben
  Umsetzungsthread: Zuerst den Worktree auf lokale Reständerungen prüfen. Bei
  Reständerungen den Closeout stoppen, die betroffenen Dateien benennen und
  erst nach ausdrücklicher Entscheidung sichern oder verwerfen.
- Ist der Worktree sauber, den zugehörigen Worktree sowie ausschließlich den
  lokalen und Remote-Feature-Branch ohne weitere Rückfrage entfernen.

## Codex-Sandbox

- `task doctor` vor gezielten Browserprüfungen verwenden. Der gemeinsame
  uv-Cache liegt unter `~/.cache/uv` und wird ausschließlich über die globale
  Codex-Konfiguration freigegeben; keine benutzerspezifische Konfiguration
  versionieren.
- Wiederkehrende bekannte Sandbox-Fehler nicht mehrfach ausführen und nicht
  durch Änderungen am Produktcode umgehen.
- Blockierte Prüfungen als Umgebungsproblem kennzeichnen und klar von echten
  Implementierungslücken trennen.
- Browser-E2E- und -a11y-Prüfungen bleiben getrennt. In der normalen
  Codex-Sandbox nicht reproduzierbare Browserfehler gezielt lokal freigeben
  oder durch CI final abnehmen lassen; Chromium nie mit `--no-sandbox` starten.
- Bei störendem Git-Fsmonitor
  `git -c core.fsmonitor=false status ...` verwenden.

Für Frontend-Arbeit gilt die [Frontend-Richtlinie](docs/developers/frontend-guidelines.md).
Für menschliche und agentische Qualitätsreviews gilt die kanonische
[Review Policy](docs/developers/reviews/index.md).
