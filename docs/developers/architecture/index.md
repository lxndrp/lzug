# Architekturübersicht

`lzug` besteht aus einem Angular-Frontend, einem Python-Anwendungskern und
einer lokalen SQLite-Instanz. Das Frontend ist das Arbeitswerkzeug für
Prüfungsausschüsse. Der FastAPI-Adapter vermittelt zwischen ihm und
den fachlichen Services; SQLAlchemy-Modelle, Repositories und Migrationen
halten den lokalen Zustand. Der frühe Prototyp unter
`prototypes/pruefungsrunde-prototyp/` ist keine Produktlaufzeit.

```text
Angular-Frontend
  -> produktiver FastAPI-HTTP-Adapter (Uvicorn)
  -> JSON-API mit OpenAPI-Vertrag
  -> frameworkfreie Anwendungsschicht, Repositories und Services
  -> SQLAlchemy-Modelle, Schema und Migrationen
  -> SQLite je Instanz
```

Die aktuelle technische Quelle liegt jeweils beim ausführbaren Vertrag:

- HTTP-Routen und OpenAPI-Antwortmodell: `backend/fastapi_app.py`; Start und
  Transportgrenzen: `backend/server.py` und `backend/transport.py`.
- Datenstruktur und deren Weiterentwicklung: `backend/models.py`,
  `db/schema.sql` und `db/migrations/`.
- Produktversion: die beim Build erzeugte `build-metadata.json`; sie leitet
  die Identität aus Commit und gegebenenfalls Release-Tag ab.
- Betriebs-, Sicherheits- und Qualitätsgrenzen: Dockerfiles, Compose-Datei,
  Taskfile und Workflows.

Die langfristigen Entscheidungen stehen als [ADRs](../decisions/index.md).
Sie erklären die gewählte Richtung, nicht deren aktuelle Endpunkt-, Feld- oder
Workflowdetails.

## Fachliche und technische Grenzen

Die [Backend-Übersicht](backend.md) ordnet die produktiven Services ihren
Schichten zu. [Authentifizierung](authentication.md),
[Benachrichtigungen](notifications.md) und der
[Ausfall- und Ersatzprozess](absence-replacement.md) beschreiben die
fachlichen Verantwortungsgrenzen. Das [fachliche Datenmodell](../domain-model.md)
erläutert Begriffe, Aggregate und Invarianten; es ersetzt kein Schema.

Die [Frontend-Richtlinie](../frontend-guidelines.md) beschreibt die
Angular-Grenze und die Qualitätsmaßstäbe. Die [OCI-Runtime](oci-runtime.md)
erläutert die Instanz-, Persistenz- und Sicherheitsgrenze für die Auslieferung.

## Laufzeit- und Bereitschaftssignale

`GET /api/health` ist ein reines Liveness-Signal des laufenden Prozesses und
liefert HTTP 200. `GET /api/ready` prüft die Anwendungs- und
Datenbankbereitschaft: ein bereiter Zustand liefert HTTP 200, ein nicht
bereiter Zustand HTTP 503. Die vollständigen Maschinenverträge gehören zur
OpenAPI-Quelle; diese Übersicht wiederholt sie nicht.

## Veröffentlichung und Betrieb

Eine Self-Hosting-Instanz gehört zu genau einem Ausschuss und speichert ihren
Zustand unter `/data`. Das OCI-Image fasst Frontend und Backend zusammen; die
[öffentliche Demo](../demo-deployment.md) bleibt eine getrennte flüchtige
Assembly mit eigenem [Kostenvertrag](../demo-cost-baseline.md). Der Release-Tag
bindet unveränderliche Artefakte und deren Build-Metadaten. Abläufe und
Nachweise liegen in den jeweiligen Runbooks und ADRs. Die lokale Kontenpflege
bleibt eine separate [Betreiber-CLI-Grenze](operator-auth-cli.md).
