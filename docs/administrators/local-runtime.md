# Lokale Laufzeit

Installieren Sie [mise](https://mise.jdx.dev/), dann richten Sie die Arbeitsumgebung ein:

```sh
mise install
task setup
```

Starten Sie Backend und Frontend mit `task dev`. Das Backend ist unter
`http://127.0.0.1:8000` verfügbar; die API-Einstiegspunkte sind `/api`,
`/api/openapi.json` und `/api/docs`. Das Frontend ist unter
`http://localhost:4200/` erreichbar.

Diese Anleitung gilt nur für die aktuelle lokale Entwicklungsinstanz. Sie beschreibt kein produktives Hosting, Backup, Restore, Upgrade oder Self-Hosting.
