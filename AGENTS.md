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
- Für jede Issue-Umsetzung einen Branch nach `codex/<issue>-<kurzer-name>`
  verwenden und nicht direkt auf `master` committen.
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

- Planung und Umsetzung eines Issues in getrennten Threads durchführen. Vor
  Beginn der Umsetzung muss die Bezeichnung des Umsetzungsthreads
  `<issue> (<type>): <title>` entsprechen; andernfalls ist sie zuerst zu
  korrigieren.
- Beim Wechsel in die Umsetzung Issue-Nummer, Ziel, Akzeptanzkriterien,
  technische Entscheidungen, Randbedingungen und offene Punkte vollständig an
  den Umsetzungsthread übergeben.
- Jeder Umsetzungsthread arbeitet ausschließlich in einem eigenen Worktree auf
  seinem Feature-Branch.
- Der Merge-Closeout erfolgt nach Merge, erfolgreicher CI und Review im selben
  Umsetzungsthread: Zuerst den Worktree auf lokale Reständerungen prüfen. Bei
  Reständerungen den Closeout stoppen, die betroffenen Dateien benennen und
  erst nach ausdrücklicher Entscheidung sichern oder verwerfen.
- Ist der Worktree sauber, den zugehörigen Worktree sowie ausschließlich den
  lokalen und Remote-Feature-Branch ohne weitere Rückfrage entfernen und den
  Umsetzungsthread archivieren.

## Codex-Sandbox

- Wiederkehrende bekannte Sandbox-Fehler nicht mehrfach ausführen und nicht
  durch Änderungen am Produktcode umgehen.
- Blockierte Prüfungen als Umgebungsproblem kennzeichnen und klar von echten
  Implementierungslücken trennen.
- Bei störendem Git-Fsmonitor
  `git -c core.fsmonitor=false status ...` verwenden.

Für Frontend-Arbeit gilt die [Frontend-Richtlinie](docs/developers/frontend-guidelines.md).
Für menschliche und agentische Qualitätsreviews gilt die kanonische
[Review Policy](docs/developers/reviews/index.md).
