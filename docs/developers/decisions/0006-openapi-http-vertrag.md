# ADR-0006: HTTP-API als OpenAPI-Vertrag

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Die ausgelieferte OpenAPI-Spezifikation in `backend/openapi.py` ist der verbindliche HTTP-Vertrag. Die JSON-API bietet Einstiegspunkt, Healthcheck, OpenAPI JSON und Swagger UI; Ressourcen verwenden REST-nahe Methoden und HAL-nahe Links.

Der Vertragstest ruft die echte HTTP-Schicht mit isolierter SQLite-Datenbank auf und validiert dokumentierte Responses gegen die ausgelieferte Spezifikation. Er prüft auch die vom Angular-`PlanningApiService` verwendeten Pfade.

## Konsequenzen

Änderungen an API-Operationen aktualisieren gemeinsam Handler, Implementierung, OpenAPI, Vertragstest und Angular-Client. Eine von der Spezifikation abweichende echte Response blockiert die Backend-Prüfung. Der frühere Detailbericht bleibt unter [api-contract-validation.md](../../development/api-contract-validation.md) erreichbar.
