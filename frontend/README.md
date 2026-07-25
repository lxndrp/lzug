# Frontend

Das Frontend ist eine Angular-22-Anwendung. Abhängigkeiten werden mit npm und
`package-lock.json` reproduzierbar installiert.

Die technische Einordnung des Frontends ist zentral in
[`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) dokumentiert.

## Entwicklungsserver

```bash
npm install
npm start
```

Die Anwendung ist danach unter `http://localhost:4200/` erreichbar. Der
Entwicklungsserver verwendet `proxy.conf.json` für die Backend-API.

## Build und Unit-Tests

```bash
npm run build:ci
npm run test:ci
npm run test:coverage
```

Die Unit-Tests verwenden Karma. Der Coverage-Lauf erzeugt HTML- und LCOV-
Reports unter `coverage/frontend`.

## Browser-Tests

Playwright startet Backend und Angular-Dev-Server automatisch:

```bash
npx playwright install chromium
npm run test:e2e
npm run test:a11y
```

Jeder Playwright-Lauf erzeugt eine eigene SQLite-Datei unter `var/e2e/` und
verwendet eigene Ports. Der ausschließlich dafür gestartete E2E-Backend-Server
setzt die Datenbank vor jedem Test auf die versionierten Demo-Seed-Daten zurück.
Dadurch bleiben Testdaten aus lokalen Entwicklungsdatenbanken ausgeschlossen;
auch einzelne Tests und parallele Läufe teilen keinen Zustand. Für eine
wiederholbare Diagnose kann der Laufname vorgegeben werden:

```bash
LZUG_E2E_RUN_ID=repeat-1 npm run test:e2e -- --grep 'updates exam round metadata'
npm run test:e2e -- --repeat-each=2 --grep 'E2E test data isolation'
```

Die CI verwendet dieselben `npm run test:e2e`- und `npm run test:a11y`-Befehle
und damit dieselbe Reset-Strategie.

Der vollständige lokale QS-Lauf ist aus dem Repository-Verzeichnis mit
`mise run quality` ausführbar.
