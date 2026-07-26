# Lokale Laufzeit

Installieren Sie [mise](https://mise.jdx.dev/) und [uv](https://docs.astral.sh/uv/), dann richten Sie die Arbeitsumgebung ein:

```sh
mise install
mise run setup
```

Starten Sie das Backend mit `.venv/bin/python -m backend.app --init --seed`. Es ist unter `http://127.0.0.1:8000` verfügbar; die API-Einstiegspunkte sind `/api`, `/api/openapi.json` und `/api/docs`.

In einem zweiten Terminal starten Sie das Frontend mit `cd frontend && npm start` und öffnen `http://localhost:4200/`.

Diese Anleitung gilt nur für die aktuelle lokale Entwicklungsinstanz. Sie beschreibt kein produktives Hosting, Backup, Restore, Upgrade oder Self-Hosting.
