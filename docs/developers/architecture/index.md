# Architekturübersicht

`lzug` besteht aus einem Angular-Frontend in `frontend/`, einem Python-Backend in `backend/`, einer lokalen SQLite-Datenbank und einem statischen frühen Prototypen unter `prototypes/pruefungsrunde-prototyp/`. Die produktive Weiterentwicklung findet im Frontend und Backend statt; der Prototyp bleibt ausschließlich fachliche und UX-bezogene Referenz.

Die zentralen Schichten sind:

```text
Angular-Frontend
  -> JSON-API mit OpenAPI-Vertrag
  -> HTTP-Handler, Repositories und Planungsservice
  -> SQLAlchemy-Modelle und Store
  -> SQLite-Datenbank
```

Python `3.14.6`, Node.js `26.5.0`, npm, `mise`, `uv` und Task sind projektweit festgelegt. Die Pins liegen in `.mise.toml`, `.python-version`, `.node-version`, `uv.lock` und `frontend/package-lock.json`; die lokalen Workflows stehen in `Taskfile.yml`.

Die Architekturentscheidungen stehen als [ADRs](../decisions/index.md). Der frühere Pfad [ARCHITECTURE.md](../../ARCHITECTURE.md) verweist auf diese gegliederte Referenz.
