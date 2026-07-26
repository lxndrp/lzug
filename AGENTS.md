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
- Pull Requests für Issue-Arbeit mit `scripts/create-issue-pr.sh` gegen
  `master` erstellen. Vollständige Umsetzungen mit `Closes #<nummer>`
  verknüpfen.
- Erst nach erfolgreicher CI und Review mergen. Worktree, lokale und Remote-
  Branches erst gemeinsam mit der Archivierung eines abgeschlossenen Issues
  aufräumen.

## Frontend

Bei Frontend-Arbeit den vollständigen Ablauf betrachten: Laden, Leerzustand,
Erfolg, Fehler, Bestätigung und Abbruch. Desktop und Mobil sowie helles und
dunkles Farbschema auf Hierarchie, Kontrast, Fokus, Umbruch, Überlauf und
erreichbare Aktionen prüfen. Interne API- oder Implementierungsbegriffe nicht
ungefiltert in der Oberfläche ausgeben.
