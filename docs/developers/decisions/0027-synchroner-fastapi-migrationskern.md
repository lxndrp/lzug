# ADR-0027: Synchroner FastAPI-Kern für die schrittweise HTTP-Migration

## Datum

2026-08-29.

## Status

Akzeptiert.

## Kontext

Der frühere HTTP-Adapter auf Basis von `BaseHTTPRequestHandler` bündelte Routing, Transportvalidierung und Fehlerabbildung in einer großen Klasse.
Die vollständige Vertragsmigration soll den Webframework-Wechsel abschließen, ohne die synchrone SQLAlchemy-, Repository- und Serviceschicht gleichzeitig neu zu entwickeln.

## Entscheidung

FastAPI ist der kanonische HTTP-Frameworkkern.
Seine Application Factory trennt Startkonfiguration, Datenbank-Readiness und vorhandene Service- beziehungsweise Repository-Factories.
Gemeinsame Abläufe liegen in einer frameworkfreien Anwendungsschicht.

Die migrierten Operationen bleiben synchrone Python-Funktionen.
FastAPI führt diese Funktionen über die von Starlette vorgesehene Threadpool-Grenze aus; Repositories und Services bleiben synchron und enthalten keine FastAPI- oder Starlette-Importe.
Eine Async-Neuentwicklung ist eine spätere, getrennt zu entscheidende Optimierung.

`python -m backend.server` ist der produktive Startpfad; der Demo-Startpfad verwendet dieselbe Factory.
Die OpenAPI-Spezifikation wird ausschließlich aus den FastAPI-Routen erzeugt.
`backend.transport` hält die synchronen Transport-Hilfen frameworkarm, während `backend.application`, Services und Repositories keine HTTP-Abhängigkeit erhalten.

## Konsequenzen

- FastAPI, Uvicorn und die TestClient-Abhängigkeit HTTPX2 sind direkt versioniert;
ihre transitiven Laufzeitabhängigkeiten bleiben über `uv.lock` reproduzierbar.
- Liveness berührt keine Datenbank. Readiness bildet den bestehenden
Anwendungs- und Datenbankvertrag ab.
- Session-Authentifizierung, aktive Ausschussmitgliedschaft, Round-Zugriff,
HATEOAS-Antwortmodell und öffentliche Datenbankfehler werden nicht dupliziert.
- Die abgeschlossene Migration wird durch fokussierte Vertragsprüfungen und
die CI-Gates abgesichert.
- Eine asynchrone Serviceschicht bleibt eine getrennte Entscheidung und
Abnahme.

## Alternativen

**Status quo dauerhaft beibehalten:** Vermeidet neue Abhängigkeiten, lässt aber die gewachsene Transportklasse und ihre manuellen Erweiterungsgrenzen bestehen.
Der Status quo bleibt nur als kontrollierter Rückfallpfad erhalten.

**Starlette direkt verwenden:** Bietet eine kleinere ASGI-Basis, würde aber Validierung, Dependency Injection und spätere OpenAPI-Integration stärker in projektindividuellen Adaptercode verlagern.
FastAPI liefert diese Migrationsbausteine auf Starlette-Basis bereits mit.

**Sofortige vollständige oder asynchrone Migration:** Würde Frameworkwechsel, Nebenläufigkeitsmodell und alle HTTP-Verträge gleichzeitig verändern.
Dieses Risiko ist für eine schrittweise, rückfallfähige Migration unnötig.

**Flask, Django oder ein Sprachwechsel:** Diese Varianten würden entweder eine weitere WSGI-Zwischengröße oder einen deutlich breiteren Plattformwechsel einführen, ohne für den minimalen Kern einen Vorteil gegenüber FastAPI zu bieten.

## Referenzen

- [ADR-0006: HTTP-API als OpenAPI-Vertrag](0006-openapi-http-vertrag.md)
- [Backend](../components.md#backend)
- [FastAPI: Nebenläufigkeit und `def`-Funktionen](https://fastapi.tiangolo.com/async/)
- [Starlette: Thread Pool](https://github.com/Kludex/starlette/blob/main/starlette/concurrency.py)
