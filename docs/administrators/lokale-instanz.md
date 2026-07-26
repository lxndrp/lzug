# Lokale Instanz betreiben

## Voraussetzungen

Installieren Sie [mise](https://mise.jdx.dev/) und [uv](https://docs.astral.sh/uv/). Für macOS kann dies beispielsweise mit `brew install mise uv` erfolgen. Andere Betriebssysteme verwenden die jeweiligen offiziellen Installationswege.

Im Repository:

```sh
mise install
mise run setup
```

Damit werden Python und Node.js in den festgelegten Versionen bereitgestellt, die Python-Abhängigkeiten aus `uv.lock` synchronisiert und die Frontend-Abhängigkeiten mit npm installiert.

## Starten

Starten Sie das Backend mit einer frischen lokalen Demo-Datenbank:

```sh
.venv/bin/python -m backend.app --init --seed --reset
```

Der Server ist unter `http://127.0.0.1:8000` verfügbar. Die API-Einstiegspunkte sind `/api`, `/api/openapi.json` und `/api/docs`.

Starten Sie anschließend in einem zweiten Terminal das Frontend:

```sh
cd frontend
npm start
```

Öffnen Sie `http://localhost:4200/`. Das Frontend nutzt den lokalen Proxy für die API.

## Lokale Daten zurücksetzen

Der Parameter `--reset` im oben gezeigten Backend-Start erzeugt die lokale Demo-Datenbank neu und lädt `db/seed_demo.sql`. Verwenden Sie ihn nur für eine lokale Entwicklungsinstanz, wenn vorhandene lokale Daten ersetzt werden dürfen.

Für technische Änderungen und Tests steht die vollständige lokale Prüfung zur Verfügung:

```sh
mise quality
```
