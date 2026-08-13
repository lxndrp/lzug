# Closeout-Monitor

Der Closeout-Monitor gleicht lokale Artefakte von Issue-Umsetzungen mit dem
GitHub-Status ab. Er ist absichtlich **rein meldend**: Der Prozess führt keine
Lösch-, Reset-, Checkout-, Fetch- oder Push-Operation aus. Die menschliche
Prüfung und der Merge-Closeout im zugehörigen Umsetzungstask bleiben
verbindlich.

## Laufintervall und Auslöser

Eine lokale Codex-Automation startet den Monitor an Werktagen um 09:00 Uhr in
der Zeitzone des Maintainer-Rechners. Zusätzlich kann ein Maintainer ihn nach
einem bestätigten Merge direkt im Hauptcheckout ausführen:

```console
python3 scripts/closeout_monitor.py
```

Die wiederkehrende Automation verwendet denselben Befehl und meldet nur dann
Handlungsbedarf, wenn noch ein lokaler Worktree, ein lokaler Feature-Branch
oder dessen Remote-Branch vorhanden ist. Der Monitor ruft absichtlich kein
`git fetch` auf: `git ls-remote` liest den tatsächlichen Remote-Stand, ohne
Tracking-Refs oder das Repository zu verändern.

## Datenquellen

Der Monitor liest ausschließlich:

- `git worktree list --porcelain` für Pfad und ausgecheckten Branch,
- `git for-each-ref` für lokale `codex/<issue>-<name>`-Branches,
- `git ls-remote --heads` für tatsächlich vorhandene Feature-Branches auf dem
  gewählten Remote,
- `git status --porcelain` im gefundenen Worktree für lokale Reständerungen,
- `gh issue view` für Issue-Zustand, Titel und URL,
- `gh pr list` für PR-, Merge-, Review- und Check-Status,
- die GitHub-GraphQL-API über `gh api graphql` für offene Review-Threads.

Ein anderer Remote oder ein explizites Repository kann angegeben werden:

```console
python3 scripts/closeout_monitor.py --remote upstream --repository lxndrp/lzug
python3 scripts/closeout_monitor.py --json
```

## Meldungen und Sicherheitsgrenzen

Jeder Fund enthält Issue, PR, Mergezustand, CI, Review, Worktree-Pfad,
Worktree-Zustand sowie lokalen und entfernten Branch. Die Ergebnisse bedeuten:

| Ergebnis | Bedeutung und nächste Aktion |
| --- | --- |
| `ready` | Issue ist geschlossen, PR gemergt, CI erfolgreich, Review geklärt und der Worktree sauber. Der zugehörige Umsetzungstask darf den Closeout nach `AGENTS.md` durchführen. |
| `branches_only` | Der Worktree fehlt bereits. Nur die noch als vorhanden gemeldeten Branches benötigen Closeout; ein bereits gelöschter Remote-Branch wird als `absent` ausgewiesen. |
| `blocked_worktree` | Der Worktree ist bewusst oder unerwartet unsauber beziehungsweise nicht lesbar. Der Closeout stoppt; die einzeln gemeldeten Änderungen werden niemals gelöscht. |
| `blocked_ci` | CI ist fehlgeschlagen, ausstehend oder nicht nachweisbar. Checks im verlinkten PR prüfen und nicht aufräumen. |
| `blocked_review` | Review ist offen, fordert Änderungen oder offene Threads konnten nicht sicher ausgeschlossen werden. Review und allgemeine PR-Befunde menschlich prüfen. |
| `not_merged` | Das Issue ist geschlossen, aber für den Branch ist kein gemergter PR nachweisbar. Ursache prüfen. |
| `not_complete` | Das Issue ist noch offen. Kein Closeout. |

Fehlen GitHub-Daten oder umfasst ein PR mehr als 100 Review-Threads, wird der
Reviewstatus konservativ `unknown` und blockiert den Closeout. Ein Merge ohne
verpflichtende Reviewentscheidung gilt nur dann als `complete`, wenn keine
offenen Review-Threads vorhanden sind; der Monitor ersetzt trotzdem nicht die
Prüfung allgemeiner PR-Kommentare, Security-Audits oder Code-Scanning-Befunde.

## Nachweis der Worktree-Schranke

`backend.tests.test_closeout_monitor.CloseoutMonitorTests` erzeugt ein
temporäres Git-Repository. Derselbe Checkout wird zunächst sauber geprüft und
anschließend durch eine absichtliche Änderung an einer versionierten Datei
unsauber gemacht. Der Test weist nach, dass nur der erste Zustand `clean`
liefert und der zweite Zustand mitsamt Dateiname als `dirty` gemeldet wird.

Der Monitor bietet bewusst keine Option zum automatischen Löschen. Auch ein
`ready`-Ergebnis ist nur eine konkrete Aufforderung an den Umsetzungstask, den
in `AGENTS.md` definierten Closeout nach bestätigtem Merge durchzuführen.
