# Frontend

Das Frontend liegt unter `frontend/` und verwendet Angular 22, TypeScript 6, Angular Router und Taiga UI. Es ist ein Arbeitswerkzeug für wiederkehrende Ausschussprozesse, keine Marketing- oder Landingpage.

Die wichtigsten Bereiche sind:

- `api/`: API-Modelle, `PlanningApiService` und `RoundContextService`.
- `dashboard/`: Status, Kennzahlen und Planungsvorschlag der aktuellen Runde.
- `exam-half-years/`: Prüfungshalbjahre und ausschussbezogene Prüfungsrunden.
- `candidates/`, `committee/`, `locations/`: Stammdatenpflege.
- `planning/`: Planungsrahmen, mögliche Tage, Verfügbarkeiten, Vorschlag und Bestätigung.

Im Entwicklungsmodus leitet `proxy.conf.json` `/api` an `http://127.0.0.1:8000` weiter. `angular.json`, `vitest.config.ts`, `playwright.config.ts` und `eslint.config.js` definieren Build, Tests und Qualitätsgrenzen.

Taiga UI wurde nach einer begrenzten Prototyp-Erprobung als Oberflächenbibliothek gewählt; die Begründung und bewusst verbleibende Ausnahmen hält [ADR-0005](../decisions/0005-taiga-ui.md) fest.
