# ADR-0004: Angular und REST-Integration

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Das Arbeitswerkzeug wird als Angular-Anwendung mit TypeScript, Angular Router und einem klaren API-Service umgesetzt. Fachliche Ansichten trennen Dashboard, Prüfungshalbjahre, Prüflinge, Ausschuss, Prüfungsorte und Planung. Der `RoundContextService` hält die aktuelle Prüfungsrunde. Die Anwendung konsumiert die JSON-API über `PlanningApiService`.

## Konsequenzen

Das Frontend wird mit npm und dem eingecheckten `package-lock.json` installiert und über einen lokalen Proxy gegen das Python-Backend entwickelt. Komponenten-, Browser- und Accessibility-Tests gehören zur Änderung. Der HTTP-Vertrag selbst ist mit [ADR-0006](0006-openapi-http-vertrag.md) festgehalten. Die aktive Übersicht steht unter [Frontend-Richtlinie](../frontend-guidelines.md).
