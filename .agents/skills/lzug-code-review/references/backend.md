# Backend-Prüfperspektive

Einstiege sind `backend/src/backend/`, `backend/tests/`, `backend/db/`, `pyproject.toml` und `uv.lock`.
Pfade dienen der Navigation; der geprüfte Stand bestimmt die tatsächlich vorhandene Struktur.

- Prüfe native FastAPI-Routen, Dependencies, Request-/Responsemodelle und den gemeinsamen OpenAPI-Vertrag.
  Beurteile Authentisierung, CSRF, Actor- und Scope-Auflösung zusammen mit der bestehenden Reihenfolge von Body-Limits, Syntax- und Feldvalidierung.
  Pydantic-Fehler dürfen keine sensiblen Eingaben spiegeln; eine bloße Umstellung auf Standardvalidierung ist kein Korrektheitsnachweis.
- Prüfe Python-Typen, strukturierte Rückgaben, Exception-Grenzen, Kontextmanager und das Zusammenspiel synchroner Services mit ASGI.
  Gezielte Nutzung von Protokollen und Dependency Injection soll konkrete Kopplungen lösen; vermeide zusätzliche Interfaces ohne erkennbaren Vertrag.
- Verfolge SQLAlchemy-Sessions, Transaktionen, Flush/Commit, Lesesnapshots, Constraints und konkurrierende Änderungen.
  Versionsprüfung und Mutation müssen den geforderten Konfliktschutz tatsächlich leisten.
  Achte auf unbeabsichtigte Zusatzsessions, Lazy Loading nach Sessionende, N+1-Zugriffe und rohe ORM-/SQL-Typen an fachlichen oder Transportgrenzen.
- Prüfe, ob Fachzustand, Revision, Audit und zugehörige Folgeaufträge entsprechend dem dokumentierten Vertrag atomar entstehen.
  Externe Zustellung und deren Wiederholung dürfen bestätigte Fachvorgänge nicht ungewollt erneut ausführen.
  Überprüfe Claim-/Retry-Abgleich und Idempotenz anhand konkreter Zustandswechsel.
- Berücksichtige bei betroffenen Pfaden sichere Dokumentnamen, begrenzte Streams, konsistente Backups, Migrationen sowie den gemeinsamen Runtime-Lifecycle von HTTP und Admin-Socket.
- Beurteile Tests nach Verhalten und relevanten Randbedingungen.
  Mock-Konfiguration, importierte Symbolnamen oder grüne Typprüfungen ersetzen keinen Nachweis von Autorisierung, Rollback und Parallelitätsverhalten.

Vertiefe den fachlichen Kontext des untersuchten Falls, ohne sämtliche Backendthemen bei jedem kleinen PR neu zu auditieren.
