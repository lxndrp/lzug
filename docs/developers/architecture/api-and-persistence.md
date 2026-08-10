# API und Qualität

Die JSON-API ist selbstbeschreibend:

- `GET /api` liefert Einstiegspunkte.
- `GET /api/health` liefert den Healthcheck.
- `GET /api/health` liefert HTTP 200 bei bereiter Datenbank und HTTP 503, wenn
  die Datenbank fehlt, nicht initialisiert oder nicht erreichbar ist.
- `GET /api/health`, `/api`, `/api/openapi.json` und `/api/docs` sind die bewusst
  öffentlichen Transport-Endpunkte; Fachoperationen benötigen eine gültige
  Session und zustandsändernde Requests zusätzlich CSRF-Schutz.
- `GET /api/openapi.json` liefert den verbindlichen OpenAPI-3.1-Vertrag.
- `GET /api/docs` liefert Swagger UI.

Kernressourcen verwenden REST-nahe CRUD-Muster mit `GET`, `POST`, `PATCH` und `DELETE`. Antworten enthalten HAL-nahe `_links`; Listen bestehen aus `items` und `_links`. Der genaue Vertrag steht immer in `backend/openapi.py`, nicht in einer zweiten statischen Liste.

Die Qualitätssicherung ist mehrschichtig: Backend mit unittest, Coverage, Ruff, Black und `pip-audit`; Frontend mit Vitest, V8-Coverage, Angular-Build, ESLint, Prettier und npm-Audit; Browser mit Playwright und axe. `task quality` führt die vollständige lokale Prüfung aus. CI verwendet getrennte Jobs und veröffentlicht die Dokumentation als Artefakt `lzug-documentation`. Der reguläre npm-Audit kann drei moderate, ausschließlich die Entwicklungsabhängigkeit `@angular/cli` betreffende Befunde über `@modelcontextprotocol/sdk` und `@hono/node-server` melden. Das produktive Sicherheitsgate prüft ohne Entwicklungsabhängigkeiten und bleibt maßgeblich.

SQLite ist die Datenbank der einzelnen Self-Hosting-Instanz. Das ausführbare
Schema liegt in `db/schema.sql`, Änderungen in `db/migrations/`;
`schema_migration` protokolliert ausgeführte Migrationen. Das Schema ist
SQLite-kompatibel und PostgreSQL-nah angelegt. Mehrzeilige Fachregeln werden in
Repository- und Service-Logik validiert. Foreign Keys, WAL,
`synchronous=NORMAL` und ein Busy-Timeout von fünf Sekunden werden pro
Verbindung konfiguriert und von der Readiness-Prüfung verifiziert. Die aktuelle
Referenz steht unter [Datenbankschema](../database-schema.md).

SQLite ist für eine kleine, einzelne Instanz je Ausschuss geeignet. Es bietet
keine zentrale Mandantenisolation und serialisiert Schreibzugriffe; eine
größere zentrale Mandantenflotte oder hohe parallele Schreiblast ist deshalb
kein stillschweigender Zielpfad dieser Erstveröffentlichung. Dafür gelten
[ADR-0013](../decisions/0013-dezentrale-instanzen-je-ausschuss.md) und
[ADR-0016](../decisions/0016-spaetere-mandantenflotte.md).

Der OpenAPI-Vertrag wird gegen echte HTTP-Responses in einer isolierten SQLite-Datenbank geprüft. Bei neuen oder geänderten Operationen sind Implementierung, OpenAPI, Vertragstest und Angular-Client zusammen anzupassen. Details zum Vertrag stehen in [ADR-0006](../decisions/0006-openapi-http-vertrag.md); den redaktionellen Prüf- und Sicherheitsprozess beschreibt das [GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung-Qualitaet-und-Sicherheit).
