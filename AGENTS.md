# Hinweise für Coding Agents

Diese Datei enthält ausschließlich Regeln für Codex und andere Coding Agents.
Produktumfang und Anleitung stehen im [README](README.md), Beiträge in
[CONTRIBUTING.md](CONTRIBUTING.md) und die technische Referenz im
[Entwicklerhandbuch](docs/developers/index.md).

## Arbeitsweise

- Vor Änderungen den aktuellen Repository- und Git-Status lesen; fremde oder
  ungefragte Änderungen niemals zurücksetzen.
- Bei Planung, Refinement oder fachlicher Klärung read-only bleiben. Umfangreiche
  Umsetzung erst im zugehörigen Issue-Worktree beginnen.
- Für Story-, Epic- und Bug-Umsetzungen einen Branch nach
  `codex/<issue>-<kurzer-name>` verwenden und nicht direkt auf `master`
  committen.
- Nur Dateien stagen, die zum Auftrag gehören. Commit-Nachrichten sind Englisch;
  deutsche Prosa verwendet korrekte Umlaute.
- Vor einer Umsetzung die betroffenen Tests ausführen und anschließend, soweit
  die Änderung es erfordert, `mise quality` verwenden. Bekannte
  Sandbox-Eigenheiten als Umgebungsthema dokumentieren, nicht mit Produktcode
  umgehen.

## GitHub-Arbeit

- GitHub Issues und das Project `lzug Roadmap` sind die dauerhafte Quelle für
  Umfang, Fortschritt und Nachverfolgung. Fortschritt und Abschluss im
  zugehörigen Issue kommentieren.
- Meldungen mit `Story:`, `Epic:` oder `Bug:` als entsprechendes GitHub Issue
  erfassen, dem Roadmap-Project hinzufügen und zunächst auf `Todo` setzen.
- Pull Requests für Issue-Arbeit mit `scripts/create-issue-pr.sh` gegen
  `master` erstellen. Vollständige Umsetzungen mit `Closes #<nummer>`
  verknüpfen.
- Erst nach erfolgreicher CI und Review mergen. Worktree, lokale und Remote-
  Branches erst gemeinsam mit der Archivierung eines abgeschlossenen Issues
  aufräumen.

## Threads und Worktrees

- Planung und Umsetzung eines Issues in getrennten Threads nach dem Muster
  `<issue> (<type>): <title>` durchführen.
- Beim Wechsel in die Umsetzung Issue-Nummer, Ziel, Akzeptanzkriterien,
  technische Entscheidungen, Randbedingungen und offene Punkte an den
  Umsetzungsthread übergeben.
- Jedem Umsetzungsthread einen separaten Worktree mit dem zugehörigen
  Feature-Branch geben.
- Nach Merge, erfolgreicher CI und Review den Umsetzungsthread archivieren und
  dabei ausschließlich seinen Worktree sowie seinen lokalen und entfernten
  Feature-Branch aufräumen.

## Codex-Sandbox

- Wiederkehrende bekannte Sandbox-Fehler nicht mehrfach ausführen und nicht
  durch Änderungen am Produktcode umgehen.
- Blockierte Prüfungen als Umgebungsproblem kennzeichnen und klar von echten
  Implementierungslücken trennen.
- Bei störendem Git-Fsmonitor
  `git -c core.fsmonitor=false status ...` verwenden.

Für Frontend-Arbeit gilt die [Frontend-Richtlinie](docs/developers/frontend-guidelines.md).
