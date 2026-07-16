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

Der vollständige lokale QS-Lauf ist aus dem Repository-Verzeichnis mit
`mise run quality` ausführbar.
