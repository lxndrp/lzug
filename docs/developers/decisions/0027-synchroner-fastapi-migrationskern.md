# ADR-0027: Synchroner FastAPI-Kern für die schrittweise HTTP-Migration

## Status

Akzeptiert am 29.08.2026.

## Kontext

Der bestehende HTTP-Adapter auf Basis von `BaseHTTPRequestHandler` bildet den
produktiven API-Vertrag vollständig ab, bündelt dabei aber Routing,
Transportvalidierung und Fehlerabbildung in einer großen Klasse. Weitere
fachliche Routen sollen schrittweise auf einen Frameworkkern migriert werden,
ohne die synchrone SQLAlchemy-, Repository- und Serviceschicht gleichzeitig
neu zu entwickeln oder den produktiven Startpfad vorzeitig umzuschalten.

## Entscheidung

FastAPI wird als zukünftiger HTTP-Frameworkkern gewählt. Ein minimaler,
ausdrücklich gestarteter Anwendungskern stellt zunächst nur `/api/health`,
`/api/ready` und `/api/round-summary` bereit. Seine Application Factory trennt
Startkonfiguration, Datenbank-Readiness und vorhandene Service- beziehungsweise
Repository-Factories. Gemeinsame Leseabläufe liegen in einer frameworkfreien
Anwendungsschicht und werden auch vom bestehenden Adapter verwendet.

Die migrierten Operationen bleiben synchrone Python-Funktionen. FastAPI führt
diese Funktionen über die von Starlette vorgesehene Threadpool-Grenze aus;
Repositories und Services bleiben synchron und enthalten keine FastAPI- oder
Starlette-Importe. Eine Async-Neuentwicklung ist eine spätere, getrennt zu
entscheidende Optimierung.

`python -m backend.app` bleibt der produktive Standard. Der FastAPI-Kern wird
nur durch gezielte Tests oder explizit mit der Factory
`backend.fastapi_app:create_app` gestartet. Die vorhandene manuelle
OpenAPI-Spezifikation bleibt während der Migration kanonisch; der partielle
FastAPI-Kern veröffentlicht keine zweite Spezifikation.

Die Migration erfolgt routenweise mit Vertragsparität. Solange der alte
Adapter vorhanden ist, bleibt er zugleich die Rückfallmöglichkeit: Der neue
Kern wird nicht gestartet beziehungsweise eine migrierte Route wird wieder nur
über den bisherigen Adapter ausgeliefert.

## Konsequenzen

- FastAPI, Uvicorn und die TestClient-Abhängigkeit HTTPX2 sind direkt versioniert;
  ihre transitiven Laufzeitabhängigkeiten bleiben über `uv.lock` reproduzierbar.
- Liveness berührt keine Datenbank. Readiness bildet den bestehenden
  Anwendungs- und Datenbankvertrag ab.
- Session-Authentifizierung, aktive Ausschussmitgliedschaft, Round-Zugriff,
  HATEOAS-Antwortmodell und öffentliche Datenbankfehler werden nicht dupliziert.
- Weitere Routen dürfen erst nach eigenem Paritätsnachweis migriert werden.
- Eine produktive Umschaltung, die Entfernung manueller OpenAPI-Teile und eine
  asynchrone Serviceschicht benötigen getrennte Entscheidungen und Abnahme.

## Alternativen

**Status quo dauerhaft beibehalten:** Vermeidet neue Abhängigkeiten, lässt aber
die gewachsene Transportklasse und ihre manuellen Erweiterungsgrenzen bestehen.
Der Status quo bleibt nur als kontrollierter Rückfallpfad erhalten.

**Starlette direkt verwenden:** Bietet eine kleinere ASGI-Basis, würde aber
Validierung, Dependency Injection und spätere OpenAPI-Integration stärker in
projektindividuellen Adaptercode verlagern. FastAPI liefert diese
Migrationsbausteine auf Starlette-Basis bereits mit.

**Sofortige vollständige oder asynchrone Migration:** Würde Frameworkwechsel,
Nebenläufigkeitsmodell und alle HTTP-Verträge gleichzeitig verändern. Dieses
Risiko ist für eine schrittweise, rückfallfähige Migration unnötig.

**Flask, Django oder ein Sprachwechsel:** Diese Varianten würden entweder eine
weitere WSGI-Zwischengröße oder einen deutlich breiteren Plattformwechsel
einführen, ohne für den minimalen Kern einen Vorteil gegenüber FastAPI zu
bieten.

## Referenzen

- [ADR-0006: HTTP-API als OpenAPI-Vertrag](0006-openapi-http-vertrag.md)
- [Backend und Datenzugriff](../architecture/backend.md)
- [FastAPI: Nebenläufigkeit und `def`-Funktionen](https://fastapi.tiangolo.com/async/)
- [Starlette: Thread Pool](https://www.starlette.io/threadpool/)
