# Entwickler-Setup

## Voraussetzungen

`mise` verwaltet die Runtime-Versionen und Entwicklungswerkzeuge; `task` führt
die lokalen Workflows aus, `uv` verwaltet Python-Umgebung und Abhängigkeiten.
Auf macOS installieren Sie mise beispielsweise mit:

```sh
brew install mise
```

Für Linux, Windows und andere Wege gelten die offiziellen Hinweise von [mise](https://mise.jdx.dev/), [uv](https://docs.astral.sh/uv/) und [Task](https://taskfile.dev/). Das Homebrew-Beispiel ist macOS-spezifisch. Auf Intel-Macs wurden extern installiertes `mise`, `uv`, Python und Node.js verwendet; der mise-interne Homebrew-/Bootstrap-Paketmanager unterstützt Intel-Macs nicht offiziell.

## Einrichten

```sh
mise install
task setup
```

Damit werden Python 3.14.6 aus `.python-version`, Node.js 26.5.0 aus `.node-version`, uv und Task 3.52.0 bereitgestellt. `task setup` erzeugt `.venv`, synchronisiert Python aus `uv.lock`, installiert das Frontend reproduzierbar mit npm und lädt den von Playwright verwendeten Chromium-Browser. Das Projekt verwendet `frontend/package-lock.json`; pnpm wird nicht verwendet.

`task doctor` prüft ohne Qualitätslauf uv, dessen gemeinsamen Cache unter
`~/.cache/uv`, `.venv` und Python sowie Node.js, npm und die tatsächlich von
Playwright verwendete Chromium-Executable. Weicht der Cache-Pfad ab, muss die
globale Codex-Freigabe korrigiert werden; benutzerspezifische Codex-Konfiguration
gehört nicht in dieses Repository.

## Lokale Entwicklung und Frontend

Starten Sie Backend und Frontend gemeinsam mit:

```sh
task dev
```

Für lokale Prüfungen stehen `task test`, `task quality:frontend`,
`task quality:e2e`, `task quality:a11y` und `task quality` bereit. Das Frontend ist unter
`http://localhost:4200/` erreichbar und nutzt `proxy.conf.json`. Vitest erzeugt
Coverage unter `coverage/frontend`. Jeder Playwright-Lauf verwendet eigene
Ports, eine eigene SQLite-Datei unter `var/e2e/` und Demo-Seed-Daten. Für
reproduzierbare Diagnosen kann `LZUG_E2E_RUN_ID` gesetzt werden.

Demo-, Unit- und Browserdaten folgen der
[kanonischen synthetischen Fixture-Grundlage](https://github.com/lxndrp/lzug/blob/master/docs/developers/development.md#synthetische-fixtures).

## VS Code

Öffnen Sie den Repository-Ordner und wählen Sie `.venv/bin/python`; `.vscode/settings.json` setzt ihn bereits voraus. Prüfen Sie Python 3.14.6, Node.js 26.5.0 sowie aktive Ruff-, Black- und ESLint-Integration.

Empfohlene Erweiterungen: `jdx.mise`, `ms-python.python`, `ms-python.debugpy`, `charliermarsh.ruff`, `dbaeumer.vscode-eslint`, `esbenp.prettier-vscode` und `ryanluker.vscode-coverage-gutters`. Die VS-Code-Tasks rufen über `mise exec -- task ...` dieselben öffentlichen `task`-Workflows für Einrichtung, Tests, Teilprüfungen, Dokumentation und die vollständige Qualitätssicherung auf. Coverage Gutters verwendet `coverage.xml` und `frontend/coverage/frontend/lcov.info`. Der Standardstart des Backends initialisiert nur die Datenbank; ein separater Debug-Start setzt Demo-Daten ausdrücklich zurück.

## Browserprüfungen in Codex und CI

`task quality:e2e` und `task quality:a11y` bleiben getrennte, parallel
ausführbare Browserteilprüfungen. In der normalen Codex-Sandbox können
Chromium-Prozesse an den Sandbox-Grenzen scheitern; das ist kein Anlass, die
Chromium-Sandbox zu deaktivieren oder Produktcode anzupassen. Führen Sie bei
Bedarf gezielt einen der beiden Browserteiltests in einer lokal freigegebenen
Umgebung aus. Die CI bleibt die finale Abnahme und führt dieselben getrennten
Browserprüfungen unverändert aus.

`task test` startet Backend- und Frontend-Tests, `task dev` beide Entwicklungsserver. Neue Python-Abhängigkeiten werden mit `uv add` und anschließend `uv sync --extra dev` ergänzt. Die Versionsdateien `.python-version`, `.node-version`, `.mise.toml`, `Taskfile.yml` und `uv.lock` bleiben versioniert.
