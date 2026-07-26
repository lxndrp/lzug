# Mitarbeit

Die verbindliche Anleitung für lokale Einrichtung, Start, Tests und Pull Requests ist `CONTRIBUTING.md` im Repository-Wurzelverzeichnis. Statusmodell, Issue- und Thread-Regeln, Qualitätsnachweise sowie Abschlussregeln stehen im [Arbeitsprozess](arbeitsprozess.md). Dieser Abschnitt ergänzt die technischen Regeln.

## Dokumentation pflegen

- Nutzer- und Administratorseiten beschreiben ausschließlich vorhandene Funktionen.
- Dauerhafte Architektur und Schnittstellen gehören in dieses Entwicklerhandbuch.
- Verbindliche HTTP-Pfade, Payloads und Antworten gehören in OpenAPI; die Anwendung liefert sie unter `/api/openapi.json` und `/api/docs` aus.
- Nicht offensichtliche öffentliche Python-Schnittstellen verwenden Google-Style-Docstrings. Exportierte Angular- und TypeScript-Schnittstellen verwenden TSDoc.

`mise run docs` baut MkDocs, die Python-Referenz und die TypeDoc-Ausgabe. Der vollständige Qualitätslauf `mise quality` enthält denselben Dokumentationsbuild.

## Änderungen an API und Datenbank

Eine API-Änderung aktualisiert gemeinsam Handler, fachliche Implementierung, `backend/openapi.py`, Vertragstest und gegebenenfalls `PlanningApiService` sowie seine Modelle. Eine Schemaänderung erhält eine versionierte Migration unter `db/migrations/`; die aktuelle Referenz bleibt [Datenbankschema](reference/datenbankschema.md).
