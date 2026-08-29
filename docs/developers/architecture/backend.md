# Backend und Datenzugriff

`backend/app.py` ist der gegenwärtige produktive, synchrone HTTP-Adapter auf
Basis von `BaseHTTPRequestHandler` und `ThreadingHTTPServer`. Er parst
Transportdaten, erzwingt Authentifizierung und Autorisierung, delegiert an
fachliche Services und bildet erwartete Fehler auf HTTP ab. Die Routen und
Request-/Response-Modelle sind derzeit in `backend/openapi.py` und dem Adapter
gebunden.

`backend/fastapi_app.py` stellt daneben den ausdrücklich zu startenden
FastAPI-Migrationsadapter bereit. Er nutzt die synchronen, frameworkfreien
Abläufe aus `backend/application.py` und den gemeinsamen Dual-Adapter-Harness.
Der produktive Standard bleibt bis zur abgeschlossenen Migration
`python -m backend.app`; die Entscheidung und Rückfallgrenze dokumentiert
[ADR-0027](../decisions/0027-synchroner-fastapi-migrationskern.md).

## Schichten und Verantwortungen

| Bereich | Produktive Verantwortung | Grenze |
| --- | --- | --- |
| HTTP und Sicherheit | `app`, `fastapi_app`, `openapi`, `auth`, `local_auth`, `authorization`, `security` | Transport, Session, CSRF, Actor- und Ausschuss-Scope; keine Fachentscheidung im Handler |
| Anwendung | `application` sowie die fachlichen Services | synchrone, frameworkunabhängige Abläufe für beide HTTP-Adapter |
| Planung und Durchführung | `planning`, `candidate_days`, `holiday_provider`, `absence` | Vorschläge, Verfügbarkeiten, bestätigte Planung und Ausfall-/Ersatzprozess |
| Fachliche Integrationen | `notifications`, `calendar`, `documents`, `document_storage` | Best-Effort-Zustellung, persönliche Kalender und atomare Dokumentablage; externe Kanäle machen den Fachvorgang nicht rückgängig |
| Persistenz | `models`, `repositories`, `store`, `database` | fachnahe Repositories und Transaktionen über SQLAlchemy; Schema und Migrationen bleiben ausführbare Quellen |
| Betrieb | `runtime_policy`, `observability`, `build_metadata`, `version`, `admin`, `admin_service` | Assembly-spezifische Erweiterungen, datensparsame Diagnose, unveränderliche Build-Identität und lokale Betreibergrenze |

Services und Repositories bleiben frameworkunabhängig. Eine neue HTTP- oder
Speichertechnik darf Fachlogik weder kopieren noch an ihr vorbeiführen.
`RuntimePolicy` trennt optionale Assembly-Routen vom Produktkern;
Benachrichtigungs- und Kalenderzustellung sind Best-Effort-Integrationen und
ändern den erfolgreichen fachlichen Zustand nicht rückwirkend.

## Persistenz und Bereitschaft

SQLite ist die Datenbank einer Self-Hosting-Instanz gemäß
[ADR-0001](../decisions/0001-lokale-relationale-persistenz.md) und
[ADR-0002](../decisions/0002-python-backend-sqlalchemy.md). Die genaue
Struktur und Weiterentwicklung liegen in `backend/models.py`, `db/schema.sql`
und `db/migrations/`; diese Seite führt keine zweite Feldreferenz.

`GET /api/health` ist reine Liveness und liefert HTTP 200, solange der Prozess
Anfragen verarbeitet. `GET /api/ready` prüft die Anwendungs- und
Datenbankbereitschaft und liefert HTTP 200 für bereit beziehungsweise HTTP 503
für nicht bereit. Details zu Konfiguration, Migration und Fehlern liegen in den
ausführbaren Verträgen und den zuständigen Betriebsquellen.
