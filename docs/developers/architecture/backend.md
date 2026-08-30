# Backend und Datenzugriff

`backend/fastapi_app.py` stellt die kanonische Application Factory für den produktiven HTTP-Vertrag bereit.
`backend/server.py` startet sie über Uvicorn; der Demo-Startpfad verwendet dieselbe Factory und ergänzt ausschließlich seine Runtime-Policy.
Transportdaten, Authentifizierung, Autorisierung und Fehlerabbildung liegen damit in einem einzigen HTTP-Adapter.

Die synchronen, frameworkfreien Abläufe aus `backend/application.py`, den fachlichen Services und den Repositories bleiben unabhängig vom Webframework.
Die Application Factory erzeugt die OpenAPI-Beschreibung aus den FastAPI- Routen; eine parallele manuelle Spezifikation oder ein Rückfalladapter existiert nicht mehr.

## Schichten und Verantwortungen

| Bereich | Produktive Verantwortung | Grenze |
| --- | --- | --- |
| HTTP und Sicherheit | `fastapi_app`, `server`, `transport`, `auth`, `local_auth`, `authorization`, `security` | Transport, Session, CSRF, Actor- und Ausschuss-Scope; keine Fachentscheidung im Handler |
| Anwendung | `application` sowie die fachlichen Services | synchrone, frameworkunabhängige Abläufe für beide HTTP-Adapter |
| Planung und Durchführung | `planning`, `candidate_days`, `holiday_provider`, `absence`, `exam_protocols`, `exam_results`, `exam_day_closures` | Vorschläge, Verfügbarkeiten, bestätigte Planung, Ausfall-/Ersatzprozess, versionierte Prüfungsprotokolle, regelgebundene Ergebnisfeststellung und formeller Tagesabschluss |
| Fachliche Integrationen | `notifications`, `calendar`, `documents`, `document_storage` | Best-Effort-Zustellung, persönliche Kalender und atomare Dokumentablage; externe Kanäle machen den Fachvorgang nicht rückgängig |
| Persistenz | `models`, `repositories`, `store`, `database` | fachnahe Repositories und Transaktionen über SQLAlchemy; Schema und Migrationen bleiben ausführbare Quellen |
| Betrieb | `runtime_policy`, `observability`, `build_metadata`, `version`, `admin`, `admin_service`, `lifecycle` | Assembly-spezifische Erweiterungen, datensparsame Diagnose, unveränderliche Build-Identität sowie lokale Betreiber- und Lifecycle-Grenze |

Services und Repositories bleiben frameworkunabhängig.
Eine neue HTTP- oder Speichertechnik darf Fachlogik weder kopieren noch an ihr vorbeiführen.
`RuntimePolicy` trennt optionale Assembly-Routen vom Produktkern; Benachrichtigungs- und Kalenderzustellung sind Best-Effort-Integrationen und ändern den erfolgreichen fachlichen Zustand nicht rückwirkend.

## Persistenz und Bereitschaft

SQLite ist die Datenbank einer Self-Hosting-Instanz gemäß [ADR-0001](../decisions/0001-lokale-relationale-persistenz.md) und [ADR-0002](../decisions/0002-python-backend-sqlalchemy.md).
Die genaue Struktur und Weiterentwicklung liegen in `backend/models.py`, `db/schema.sql` und `db/migrations/`; diese Seite führt keine zweite Feldreferenz.

`GET /api/health` ist reine Liveness und liefert HTTP 200, solange der Prozess Anfragen verarbeitet.
`GET /api/ready` prüft die Anwendungs- und Datenbankbereitschaft und liefert HTTP 200 für bereit beziehungsweise HTTP 503 für nicht bereit.
Details zu Konfiguration, Migration und Fehlern liegen in den ausführbaren Verträgen und den zuständigen Betriebsquellen.
