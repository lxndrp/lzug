# Continuous Integration

## Workflow-Verantwortungen

Die GitHub-Actions-Landschaft bleibt nach Verantwortung getrennt. Der
Kernworkflow `CI` bündelt die voneinander abhängige Pfadklassifikation und den
einzigen Gesamtstatus für Backend, Frontend, npm-Security, technische
Dokumentation, Compose, Browser-E2E und Accessibility. Eine weitere Aufteilung
dieser Jobs würde Klassifikation oder Gate über Workflow-Grenzen duplizieren,
ohne die ausgeführten Qualitätsverträge zu verkleinern.

| Workflow | Auslöser und Verantwortung |
| --- | --- |
| `CI` | Jeder Pull Request und Push nach `main` oder `master`; zusätzlich wöchentlicher und manueller Vollauf. |
| `Security` | Eigenständige CodeQL-, Secret- und Misconfiguration-Gates für Pull Requests, Pushes und manuelle Läufe. |
| `Operator CLI` | Go-Vertrag und portable Builds für Pull Requests, Pushes und manuelle Läufe. |
| `OCI` | Eigene konservative Runtime-Pfadklassifikation, einmaliger Image-Build, Runtime-Smoke, Scan, SBOM und Gesamtgate. |
| `Dependabot auto-merge` | Ausschließlich Metadatenprüfung geeigneter Dependabot-PRs über `pull_request_target`; kein Checkout und keine Ausführung von PR-Code. |
| `Wiki pre-publish` | Ausschließlich manuell für einen angegebenen Stand des separaten Wiki-Repositorys. |
| `Wiki post-publish` | Nach einer Wiki-Veröffentlichung oder manuell; keine Kopplung an Pull Requests des Hauptrepositorys. |

Damit verändern Pull Requests weder Release- noch Wiki-Publishing-Trigger. Die
eigenständigen Security-, Operator- und OCI-Gates behalten ihre eigene
Verantwortung; die folgende Klassifikation steuert ausschließlich die Jobs im
Kernworkflow `CI`.

## Konservative Pfadklassifikation

`CI` startet bei jedem Pull Request zunächst `Change classification` und endet
immer mit `CI overall`. Der Gesamtstatus prüft sowohl den Klassifizierer als
auch jeden ausgewählten Job. Ein nicht ausgewählter Job muss ausdrücklich den
Status `skipped` haben; ein ausgewählter Job muss erfolgreich sein. Dadurch
kann `CI overall` als stabiler Required Check verwendet werden, während die
Einzeljobs Diagnoseinformationen liefern.

Die Klassifikation wird über `scripts/classify_ci_paths.py` zentral und mit
Unit-Tests gepflegt. Mehrere Pfade vereinigen ihre Jobmengen. Eine leere,
unbekannte oder gemeinsame Grenze sowie Änderungen an Workflows, Toolchain oder
übergreifender Konfiguration erzwingen fail-closed den vollständigen Lauf.

| Änderung | Ausgewählte CI-Jobs |
| --- | --- |
| Reine Prozess- und Metadaten, etwa `AGENTS.md` | keine fachlichen Kernjobs |
| `docs/**`, `mkdocs.yml` oder technische README-Dateien | Dokumentation |
| `backend/tests/**` oder statische Prototyp-Testhilfen | Backend |
| Produktives `backend/**`, `db/**`, Schema, Migrationen oder synthetische Fixtures | Backend, Dokumentation, Browser-E2E, Accessibility |
| Frontend-Produktcode und produktive Build-Konfiguration | Frontend, Dokumentation, Browser-E2E, Accessibility |
| Reine Frontend-Unit-Tests und zugehörige Unit-/Lint-Konfiguration | Frontend |
| Playwright-Tests, Playwright-Konfiguration oder E2E-Server | Browser-E2E, Accessibility |
| `uv.lock` | Backend, Dokumentation, Browser-E2E, Accessibility |
| `frontend/package.json` oder `frontend/package-lock.json` | Frontend, npm-Security, Dokumentation, Browser-E2E, Accessibility |
| Compose-Konfiguration und deren Validierungsskript | Compose |
| Reine Operator- oder OCI-Grenzen | keine Kernjobs; die eigenen Workflows bleiben maßgeblich |
| CI, Toolchain, gemeinsame Skripte, gemischte unbekannte Grenzen | vollständiger Kernworkflow |

Pushes nach `main` oder `master`, der wöchentliche Zeitplan und
`workflow_dispatch` umgehen die Pfadauswahl bewusst und führen alle Kernjobs
aus. E2E und Accessibility bleiben dabei getrennte Jobs.

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

Task klassifiziert lokal weiterhin keine Pfade. Für eng begrenzte Änderungen
werden die dokumentierten `quality:*`-Teilaufgaben gewählt; bei unklaren,
querschnittlichen oder Toolchain-Änderungen bleibt `task quality` der Vollauf.
Dieser umfasst bewusst auch Operator und Compose, aber weder Image-Build noch
Runtime-Smoke. Die kompakte lokale Auswahlmatrix steht in
[ADR-0009](decisions/0009-toolchain-und-entwicklungs-tasks.md).
