# Entwickler-Setup

## Voraussetzungen

`mise` verwaltet die Runtime-Versionen; `uv` verwaltet Python-Umgebung und Abhängigkeiten. Auf macOS installieren Sie beide beispielsweise mit:

```sh
brew install mise uv
```

Für Linux, Windows und andere Wege gelten die offiziellen Hinweise von [mise](https://mise.jdx.dev/) und [uv](https://docs.astral.sh/uv/). Das Homebrew-Beispiel ist macOS-spezifisch. Auf Intel-Macs wurden extern installiertes `mise`, `uv`, Python und Node.js verwendet; der mise-interne Homebrew-/Bootstrap-Paketmanager unterstützt Intel-Macs nicht offiziell.

## Einrichten

```sh
mise install
mise run setup
```

Damit werden Python 3.14.6 aus `.python-version` und Node.js 26.5.0 aus `.node-version` installiert, `.venv` mit `uv venv --python "$(mise which python)" --clear --seed` erzeugt, Python aus `uv.lock` synchronisiert und das Frontend mit npm installiert. Das Projekt verwendet `frontend/package-lock.json`; pnpm wird nicht verwendet.

Alternativ:

```sh
uv venv --python "$(mise which python)" --clear --seed
uv sync --locked --extra dev
cd frontend && npm install
```

## Lokale Entwicklung und Frontend

Starten Sie Backend und Demo-Daten mit `.venv/bin/python -m backend.app --init --seed --reset`. Die API läuft unter `http://127.0.0.1:8000/api/`; OpenAPI und Swagger UI unter `/api/openapi.json` und `/api/docs`.

```sh
cd frontend
npm start
npm run build:ci
npm run test:ci
npm run test:coverage
npx playwright install chromium
npm run test:e2e
npm run test:a11y
```

Das Frontend ist unter `http://localhost:4200/` erreichbar und nutzt `proxy.conf.json`. Karma erzeugt Coverage unter `coverage/frontend`. Jeder Playwright-Lauf verwendet eigene Ports, eine eigene SQLite-Datei unter `var/e2e/` und Demo-Seed-Daten. Für reproduzierbare Diagnosen kann `LZUG_E2E_RUN_ID` gesetzt werden.

## VS Code

Öffnen Sie den Repository-Ordner und wählen Sie `.venv/bin/python`; `.vscode/settings.json` setzt ihn bereits voraus. Prüfen Sie Python 3.14.6, Node.js 26.5.0 sowie aktive Ruff-, Black- und ESLint-Integration.

Empfohlene Erweiterungen: `jdx.mise`, `ms-python.python`, `ms-python.debugpy`, `charliermarsh.ruff`, `dbaeumer.vscode-eslint`, `esbenp.prettier-vscode` und `ryanluker.vscode-coverage-gutters`. VS-Code-Tasks decken Backend- und Frontend-Tests, Coverage, Browser, Sicherheit und den vollständigen Qualitätslauf ab. Coverage Gutters verwendet `coverage.xml` und `frontend/coverage/frontend/lcov.info`.

`mise run test` startet Backend- und Frontend-Tests, `mise run dev` beide Entwicklungsserver. Neue Python-Abhängigkeiten werden mit `uv add` und anschließend `uv sync --extra dev` ergänzt. Die Versionsdateien `.python-version`, `.node-version`, `.mise.toml` und `uv.lock` bleiben versioniert.
