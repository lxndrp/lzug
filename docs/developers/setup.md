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

Damit werden Python 3.14.6 aus `.python-version`, Node.js 26.5.0 aus `.node-version`, uv und Task 3.52.0 bereitgestellt. `task setup` erzeugt `.venv`, synchronisiert Python aus `uv.lock` und installiert das Frontend reproduzierbar mit npm. Das Projekt verwendet `frontend/package-lock.json`; pnpm wird nicht verwendet.

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

## VS Code

Öffnen Sie den Repository-Ordner und wählen Sie `.venv/bin/python`; `.vscode/settings.json` setzt ihn bereits voraus. Prüfen Sie Python 3.14.6, Node.js 26.5.0 sowie aktive Ruff-, Black- und ESLint-Integration.

Empfohlene Erweiterungen: `jdx.mise`, `ms-python.python`, `ms-python.debugpy`, `charliermarsh.ruff`, `dbaeumer.vscode-eslint`, `esbenp.prettier-vscode` und `ryanluker.vscode-coverage-gutters`. VS-Code-Tasks decken Backend- und Frontend-Tests, Coverage, Browser, Sicherheit und den vollständigen Qualitätslauf ab. Coverage Gutters verwendet `coverage.xml` und `frontend/coverage/frontend/lcov.info`.

`task test` startet Backend- und Frontend-Tests, `task dev` beide Entwicklungsserver. Neue Python-Abhängigkeiten werden mit `uv add` und anschließend `uv sync --extra dev` ergänzt. Die Versionsdateien `.python-version`, `.node-version`, `.mise.toml`, `Taskfile.yml` und `uv.lock` bleiben versioniert.
