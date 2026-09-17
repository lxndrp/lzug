# Werkzeuginventar

Dieses Inventar hält für jeden ausführbaren Einstieg den aktuellen Eigentümer,
die direkten Aufrufer und den eigenständigen Vertrag fest.
Generische Format-, Link-, Build- und Testaufgaben bleiben bei den jeweiligen
Standardwerkzeugen.
Die Liste ist keine zweite Test- oder API-Dokumentation.

## Verbleibende repositoryweite Einstiegspunkte

| Einstieg | Eigentümer und direkte Aufrufer | Eigenständiger Vertrag und Entscheidung |
| --- | --- | --- |
| `scripts/build-frontend.ps1` | Frontend; `frontend/package.json`, Dockerfiles | Staged die exakt benötigten Brand- und Build-Metadaten und ruft Angular mit der gewählten Konfiguration auf. Der PowerShell-Adapter bleibt plattformübergreifend und enthält keine Frontendfachlogik. |
| `scripts/build_metadata.py` | Repository-/Buildgrenze; Dockerfiles, Taskfile, Demo- und Releaseabläufe | Liefert die fail-closed Identität aus Tag, Revision und Version für Backend, Frontend, OCI und CLI. Behalten als gemeinsam genutzten Produktmetadatenvertrag. |
| `scripts/check_documentation.py` | Dokumentation; `task docs:check` | Prüft nur den aktuellen Dokumentationsbaum, MkDocs-Navigation, ADR-Status, den entfernten Repository-Handbuchbestand und Root-Grenzen. Link-, Markdown- und Buildprüfung verbleiben bei MkDocs/Hugo. |
| `tests/pester/Container.Tests.ps1` | OCI/Self-Hosting; `task quality:pester` | Maßgeblicher Pester-Vertrag für Image-, Runtime- und Compose-Grenzen. |
| `scripts/demo-container-smoke.sh` | Öffentliche Demo; `task quality:demo` | Beweist den separaten App-/Seed-Containervertrag einschließlich Seed-Revision, Runtime-Policy und Wiederanlaufgrenzen. Behalten, weil der allgemeine Produktimage-Smoke diese Demo-Paarung nicht abdeckt. |
| `tests/pester/Compatibility.Tests.ps1` | Kompatibilitätstests; `task quality:pester` | Hält den unterstützten Upgradepfad als Pester-Kompatibilitätsvertrag sichtbar. |
| `scripts/sbom.py` | Delivery/OCI; Qualitäts-, PR- und Release-Workflows | Erzeugt keine SBOMs mehr; Dependency-, Image- und CLI-Scans laufen als direkte gepinnte Syft-Aufrufe in Task und Workflows. Behalten bleiben die CycloneDX-Identität, die deterministische Release-Aggregation und die Validierung, die kein Standardwerkzeug ausdrückt. |
| `scripts/validate_demo_url_contract.py` | Öffentliche Publikation; Publication-Workflow und Vertragstests | Erzwingt die erlaubte kanonische HTTPS-Origin ohne Credentials, Pfad oder fremde Demo-/Stage-Hosts. Behalten als Sicherheitsgrenze der konfigurierten Publikation. |

## Komponentenbezogene Werkzeuge außerhalb von `scripts/`

| Einstieg | Eigentümer und Aufrufer | Entscheidung |
| --- | --- | --- |
| `brand/generate-assets.mjs` | Brand; `task brand:generate` und `task brand:check` | Ein einziger Einstieg erzeugt und prüft die tatsächlich ausgelieferten Derivate, Quellen, Tokens und Lizenzen. Die beiden früheren Brand-Skripte wurden nicht zusammenkopiert, sondern als ein gemeinsamer Vertrag mit einer Eigentümergrenze zusammengeführt. |
| `docs/media/check.py` | Dokumentation/Publikation; `task docs:media:check` | Prüft die von Playwright erzeugten PNG-Dateien und die dazugehörigen Fixture-/Viewport-Metadaten mit dem Standardwerkzeug `file`. Behalten als kleiner Medienvertrag; ein eigener PNG-Parser ist entfernt. |
| `docs/publication/` und `backend.fastapi_assembly` | Dokumentation/Publikation; `task docs:publication*` und der Publication-Workflow | Eingechecktes Hugo-Projekt mit Blowfish-Modulpin; der direkt ausführbare kanonische FastAPI-Assembly-Einstieg schreibt das OpenAPI-Dokument. Hugo, TypeDoc, Git und Lychee werden direkt über Task aufgerufen. Wiki-Inhalte bleiben im GitHub Wiki; die generische Linkprüfung bleibt beim Standardwerkzeug. |
| `scripts/run-pester.ps1` | OCI, Compose und Kompatibilität; `task quality:pester` | Installiert die gepinnte Pester-Version und erzeugt den standardisierten NUnit-Report. |

## Entfernte Einstiege

`check_brand_references.mjs`, `render_brand_review.mjs` und die historischen
Brand-Nachweise wurden mit #637 entfernt.
Der abgelöste Prototyp und sein Adapter wurden mit #638 entfernt.
Die einmalige Wiki-Migration und ihre Dauerverträge wurden mit #640 entfernt.
`compose-command.sh` und `validate-compose.sh` waren dünne Wrapper und sind
durch direkte, im Taskfile sichtbare Docker-Aufrufe ersetzt.
`check_demo_media.py` wurde nach `docs/media/check.py` verlagert und auf den
kleinen Metadatenvertrag mit dem Standardwerkzeug `file` reduziert.
Die SBOM-Erzeugung aus `scripts/sbom.py` wurde mit #811 durch direkte gepinnte
Syft-Aufrufe in Task und Workflows ersetzt.
`scripts/verify_cli_release.py` wurde mit #811 entfernt;
die Reproduzierbarkeitsprüfung der CLI übernimmt GoReleaser zusammen mit dem
Build-Metadaten-Vertragstest des Ziel-Go-Moduls.
`scripts/export_openapi.py` wurde mit #811 entfernt;
der direkt ausführbare kanonische FastAPI-Assembly-Einstieg erzeugt das
OpenAPI-Dokument für die Publikation.
