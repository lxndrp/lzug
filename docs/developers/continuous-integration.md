# Continuous Integration

## Stabiler Qualitätsvertrag

Pull Requests werden nach sieben Qualitätsdomänen geprüft. Ihre folgenden
Gate-Namen sind die öffentliche, für Rulesets und nachgelagerte Release-Regeln
verbindliche Schnittstelle:

| Stabiler Check | Erfolgsbedingung |
| --- | --- |
| `Quality / Backend` | Alle ausgewählten Python-Prüfungen einschließlich Abhängigkeitsaudit sind erfolgreich; andernfalls sind die Detailjobs nachweislich übersprungen. |
| `Quality / Frontend` | Alle ausgewählten Angular-Prüfungen und der bei Abhängigkeitsänderungen ausgewählte npm-Sicherheitscheck sind erfolgreich oder nachweislich übersprungen. |
| `Quality / Operator CLI` | Go-Vertrag und alle portablen Builds sind erfolgreich oder nachweislich übersprungen. |
| `Quality / OCI` | Image-Build, Runtime-Smoke, Scan und SBOM sind erfolgreich oder nachweislich übersprungen. |
| `Quality / Documentation` | Die ausgewählte technische Dokumentation ist erfolgreich gebaut oder nachweislich übersprungen. |
| `Quality / Security` | Der immer ausgeführte Secret-/Misconfiguration-Scan und gegebenenfalls CodeQL sind erfolgreich. |
| `Quality / Overall` | Alle ausgewählten systemübergreifenden Detailverträge sind erfolgreich; nicht ausgewählte Details sind nachweislich übersprungen. |

Jedes Gate läuft mit `if: always()` und prüft Klassifizierergebnis,
Auswahlflag und Detailjobstatus. Ein ausgewählter Detailjob muss `success`, ein
nicht ausgewählter `skipped` melden. Leere oder fehlende Ausgaben lassen das
Gate fehlschlagen. Interne Jobnamen dürfen sich ändern, diese sieben Namen und
ihre Semantik dagegen nicht ohne kontrollierte Migration der Required Checks.

Bis zur Ruleset-Migration in #305 bleiben `CI overall` und
`OCI pull request gate` als reine Kompatibilitätschecks sichtbar. Sie hängen
von den neuen Gates ab und können diese daher nicht umgehen. Die bisher
erforderlichen CodeQL-, Source-Scan- und OCI-Scan-Kontexte bleiben ebenfalls
erhalten; ein nicht ausgewählter Detailjob meldet dabei `skipped`.

Die Detailjobs bleiben bis zu ihrer weiteren Konsolidierung auf `CI`,
`Operator CLI`, `OCI` und `Security` verteilt. Alle vier Workflows verwenden
bereits dieselbe Klassifikation; es gibt keine eigene OCI- oder CLI-Pfadmatrix.
Wiki-Publishing und Dependabot-Auto-Merge bleiben ereignisbasierte, unabhängige
Automationen.

## Zentrale, konservative Pfadklassifikation

`scripts/classify_quality_paths.py` ist die einzige Quelle für die
Domänenauswahl Backend, Frontend, Betreiber-CLI, OCI, Dokumentation, Security
und Overall. Interne Flags wählen zusätzlich npm-Audit, CodeQL, Compose,
Browser-E2E und Accessibility aus. Mehrere geänderte Pfade vereinigen ihre
Auswahlmengen.

| Änderung | Ausgewählte Domänen und Details |
| --- | --- |
| Reine Prozess- und Metadaten, etwa `AGENTS.md` | keine Anwendungsdomäne; nur Klassifizierer, stabile Gates und der bewusst breite Source-Scan |
| `docs/**`, `mkdocs.yml`, Changelog oder technische README-Dateien | Dokumentation |
| `backend/tests/**` oder statische Prototyp-Testhilfen | Backend |
| Produktives `backend/**`, `db/**`, Schema, Migrationen oder Fixtures | Backend, OCI, Dokumentation, Security und Overall mit getrennten E2E-/a11y-Details |
| Betreiberprotokoll in `backend/admin.py` oder `backend/admin_service.py` | wie produktives Backend, zusätzlich Betreiber-CLI |
| Frontend-Produktcode und produktive Build-Konfiguration | Frontend, OCI, Dokumentation, Security und Overall mit getrennten E2E-/a11y-Details |
| Reine Frontend-Unit-Tests und zugehörige Unit-/Lint-Konfiguration | Frontend |
| Playwright-Tests, Playwright-Konfiguration oder E2E-Server | Overall mit getrennten E2E-/a11y-Details |
| `uv.lock` | Backend, OCI, Dokumentation, Security und Overall |
| `frontend/package.json` oder `frontend/package-lock.json` | Frontend einschließlich npm-Audit, OCI, Dokumentation, Security und Overall |
| Reiner Go-Code oder `go.mod` | Betreiber-CLI; keine Browser- oder OCI-Prüfung |
| Dockerfile, Docker-Kontext oder Container-Smoke | OCI und Overall |
| Compose-Konfiguration und deren Laufzeitvertrag | Overall mit Compose-Detail |
| Security-Gate-Logik | Security mit CodeQL |
| CI, Toolchain, gemeinsame Qualitätsskripte, leere oder unbekannte Grenzen | fail-closed alle Domänen und Details |

Pushes nach `main` oder `master`, der wöchentliche CI-Zeitplan und manuelle
Läufe verwenden `--full-reason` und wählen unabhängig von geänderten Pfaden
alles aus. Die Klassifikations- und Workflow-Verträge werden als Python-Tests
ausgeführt.

## Release-Trennung

Normale Qualitätsworkflows reagieren ausschließlich auf Pull Requests, Branch-
Pushes, Zeitplan oder manuellen Vollauf. Sie besitzen weder Schreibrecht auf
Packages noch einen Veröffentlichungsschritt. Nur `.github/workflows/release.yml`
reagiert auf `vMAJOR.MINOR.PATCH`-Tags und darf GHCR-Inhalte oder GitHub
Releases veröffentlichen. Ein normaler Pull Request, Merge oder erfolgreicher
Qualitätslauf löst deshalb niemals eine Veröffentlichung aus.

## Playwright-Browsercache

Beide Browserjobs verwenden weiterhin
`npx playwright install --with-deps chromium`. Davor wird
`~/.cache/ms-playwright` mit einem Schlüssel aus Betriebssystem, Architektur und
der in `frontend/package-lock.json` gelockten `@playwright/test`-Version
wiederhergestellt. Ein Cache-Treffer ersetzt nur den Browserdownload, nicht die
Installation beziehungsweise Prüfung der Systemabhängigkeiten.

Bei Änderungen am Cache-Vertrag werden ein kalter Lauf und die warme
Wiederholung desselben Commits verglichen. Maßgeblich sind Cache-Treffer,
Installationsdauer und gesamte Dauer beider Browserjobs. Der konkrete Nachweis
gehört in den umsetzenden Pull Request; der Cache bleibt nur bei reproduzierbar
kürzerer Laufzeit und stabilen E2E-/Accessibility-Ergebnissen bestehen.

## Lokale Auswahl

Der Klassifizierer entscheidet die gehostete Auswahl. Lokal entsprechen ihm
die Teilaufgaben `task quality:backend`, `task quality:frontend`,
`task quality:operator`, `task docs`, `task quality:compose`,
`task quality:e2e` und `task quality:a11y`. Der produktive npm-Audit liegt in
`task quality:security` und ergänzt Frontend-Abhängigkeitsänderungen. OCI-Build,
Image-Scan, Container-Runtime-Smoke, CodeQL und der gehostete Source-Scan
bleiben artefakt- beziehungsweise GitHub-gebunden; lokal decken die betroffenen
Backend-/Frontend-Tasks und fokussierten Vertragstests die Änderung ab.

Für eng begrenzte Änderungen werden nur die betroffenen Teilaufgaben gewählt.
Produktive Web-Grenzen ergänzen E2E und a11y getrennt, Compose-Grenzen
`quality:compose`. Bei CI-, Toolchain-, Security-, gemeinsamen oder unklaren
Änderungen bleibt `task quality` der lokale Vollauf. Vor Browserprüfungen ist
`task doctor` auszuführen. Die allgemeine lokale Auswahlmatrix steht ergänzend
in [ADR-0009](decisions/0009-toolchain-und-entwicklungs-tasks.md).
