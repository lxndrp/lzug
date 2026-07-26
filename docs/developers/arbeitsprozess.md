# Arbeitsprozess für Planung und Beiträge

GitHub Issues und das Project **lzug Roadmap** sind die dauerhafte Quelle für Backlog, Prioritäten, Iterationen, Termine, Meilensteine und Fortschritt. Repository-Dokumente enthalten versionierten Produkt-, Architektur- und Entscheidungsstand; Chat und lokale Notizen sind nur Arbeitsgedächtnis.

## Arbeitselemente und Status

Neue Epics, Stories, Tasks und Bugs werden als GitHub Issues geführt und erhalten genau ein `type:`-Label: `epic`, `story`, `task` oder `bug`. Epics und Stories werden als Parent/Sub-Issues verknüpft. `resolution:`-Labels (`duplicate`, `invalid`, `wontfix`, `help-wanted`) beschreiben bei Bedarf die abschließende Einordnung. Dependabot-Labels können zusätzlich bestehen.

Das Roadmap-Project verwendet `Todo`, `In Progress` und `Done`. Geschlossene Issues werden nicht gelöscht. Wesentliche Prognose-, Fortschritts- oder Risikoänderungen erhalten ein Project-Status-Update mit Berichtsdatum, Prognose, Fortschritt, kritischem Pfad und Risiken. Kleine Feldpflege und redaktionelle Korrekturen benötigen kein eigenes Update.

Meldungen im Format `Epic: <Titel>`, `Story: <Titel>` oder `Bug: <Titel>` werden als entsprechendes Issue mit den verfügbaren Details angelegt, dem Roadmap-Project hinzugefügt und zunächst auf `Todo` gesetzt. Fehlende Details sind vor einer umfangreichen Umsetzung zu klären.

Refinements von Stories und Epics aktualisieren Titel, Beschreibung, Labels oder Verknüpfungen. Bei Bugs bleibt die ursprüngliche Fehlerbeschreibung erhalten; zusätzliche Erkenntnisse kommen als Kommentar hinzu. Ein Project-Status ändert sich nur bei tatsächlichem Fortschritt oder neuer Priorisierung.

## Planung, Umsetzung und Nachweise

Planung, Refinement und fachliche Klärung erfolgen getrennt von der Umsetzung. Threads für Issues verwenden das Muster `<issue> (<type>): <title>`. Jeder Umsetzungsthread hat einen eigenen Worktree und Feature-Branch; beim Übergang werden Issue-Nummer, Ziel, Akzeptanzkriterien, technische Entscheidungen, Randbedingungen und offene Punkte übergeben.

Der Implementierungsstand wird im zugehörigen Issue kommentiert: an sinnvollen Zwischenständen Umfang und Verifikation, Abweichungen und offene Punkte, vor Abschluss zusätzlich Pull Request und mögliche Folgearbeit. Fortschritt darf nicht ausschließlich im Chat stehen.

## Branches, Pull Requests und Abschluss

Produkt- und Fehlerbehebungsarbeiten zu Issues entstehen auf `codex/<issue>-<kurzer-name>`, nie direkt auf `master`. Commits bleiben klein, thematisch und auf Englisch. Vor dem Commit werden nur auftragsbezogene Dateien gestaged; bei lokal störendem fsmonitor hilft `git -c core.fsmonitor=false status`.

Issue-Pull-Requests werden mit `scripts/create-issue-pr.sh` gegen `master` erstellt. Das Script übernimmt Project, Milestone und Assignees aus dem Issue. Vollständige Umsetzungen verwenden `Closes #<nummer>`, Teilumsetzungen eine nicht schließende Verknüpfung. Erst erfolgreiche CI und Review erlauben Merge. Danach werden das Issue auf `Done` gesetzt und geschlossen, sofern vollständig. Archivierung eines zugehörigen Threads erfolgt gemeinsam mit dem Entfernen genau des Issue-Worktrees sowie der lokalen und Remote-Feature-Branches; `master`, andere Issues und aktive Arbeitsverzeichnisse bleiben unberührt.

## Verifikation und Sandbox

`mise quality` ist grundsätzlich die maßgebliche lokale Gesamtprüfung. Teilprüfungen dürfen vorangehen, wenn sie die Änderung klar eingrenzen. Die GitHub-Actions-Pipeline ist nach erfolgreicher lokaler Prüfung die finale Abnahme. Abschlussberichte unterscheiden klar zwischen **verifiziert**, **in Codex nicht verifizierbar** und **durch bekannte Sandbox-Grenze blockiert**.

Bekannte Eigenheiten der Codex-Sandbox rechtfertigen keinen Produktfix: `git status` kann durch fsmonitor stören, und Frontend-Builds oder Browser-/E2E-nahe Prüfungen können abweichen. Einen wiederkehrenden bekannten Umgebungstreffer nicht mehrfach wiederholen; stattdessen Befund und verbleibende Produktlücken getrennt dokumentieren.
