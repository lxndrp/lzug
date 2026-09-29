# Werkzeuginventar

Dieses Inventar hält für jeden ausführbaren Einstieg den aktuellen Eigentümer,
die direkten Aufrufer und den eigenständigen Vertrag fest.
Generische Format-, Link-, Build- und Testaufgaben bleiben bei den jeweiligen
Standardwerkzeugen.
Die Liste ist keine zweite Test- oder API-Dokumentation.
Die Vorrang- und Zuständigkeitsregel steht in
[ADR-0039](decisions/0039-deklarative-toolchain-zustaendigkeiten.md).
Stabile Werkzeug-Policy liegt in nativer Konfiguration; konkrete Ziele und
laufbezogene Parameter bleiben beim Aufruf.
Verbleibende komponenteneigene Logik gehört in die jeweilige Komponente,
notwendiges Querschnitts- und Repository-Skripting in PowerShell.

Die Einträge beschreiben den aktuellen Tree.
Eine Sprachänderung oder ein Verschieben von generischer Orchestrierung gilt
allein nicht als Vereinfachungsnachweis.

## Verbleibende repositoryweite Einstiegspunkte

| Einstieg | Eigentümer und direkte Aufrufer | Eigenständiger Vertrag und Entscheidung |
| --- | --- | --- |
| `scripts/build-frontend.ps1` | Frontend; `frontend/package.json` | Staged lokal fehlende Brand- und Build-Metadaten, erzeugt bei direkten npm-Aufrufen die Transporttypen mit den nativen Python- und openapi-ts-Einstiegen und ruft Angular für Build, Watch oder Serve auf. Im Taskgraph erledigt der explizite Task die Transportgenerierung davor. Der Adapter ruft Task nicht verschachtelt auf und entfernt im Fehlerfall ausschließlich selbst angelegte Dateien. |
| `scripts/operator-reproducibility.ps1` | Betreiber-CLI; `operator:packaging-and-reproducibility` | Führt genau zwei saubere GoReleaser-Builds aus, liest die tatsächlichen Archive und Binaries aus `artifacts.json`, vergleicht ihre SHA-256-Werte und prüft auf unterstützten Hosts die CLI-Metadaten. Lehnt vorhandene `dist`- und GoReleaser-Arbeitsdateien ab und entfernt nur die während des Laufs erzeugten Dateien. |
| `tests/pester/Container.Tests.ps1` | OCI/Self-Hosting; `task quality:container`, `quality:compose`, vollständige Quality-Suite | Prüft Imageidentität, Runtime-Rechte, Frontend-/Health-Auslieferung, CLI-Socketanbindung und einen Daten-Roundtrip über Container-Neuerstellung. |
| `tests/pester/Operator.Tests.ps1` | Betreiber-CLI; `task quality:operator-container`, vollständige Quality-Suite | Prüft den interaktiven CLI-Einstieg des gebauten Produkt-Binaries über ein echtes Pseudoterminal. |
| `scripts/demo-container-smoke.sh` | Öffentliche Demo; `demo:quality` | Beweist den separaten App-/Seed-Containervertrag einschließlich Seed-Revision, Runtime-Policy und Wiederanlaufgrenzen. Behalten, weil der allgemeine Produktimage-Smoke diese Demo-Paarung nicht abdeckt. |
| `tests/pester/Compatibility.Tests.ps1` | Kompatibilitätstests; `task quality:pester` | Führt Legacy-Restore, explizite Socketmigration und Wiederanlauf mit der digestgebundenen v0.6.0-Fixture aus. |
| `.syft.yaml` | Delivery/OCI; Quality- sowie Produkt- und Demo-Publish-Workflows | Hält die portable scannerweite Policy deklarativ. Syft erzeugt direkt die SBOMs der veröffentlichten OCI-Images; Scan-Ziele, Ausgabe und der flüchtige Cache bleiben sichtbar bei den Aufrufen. |

## Komponentenbezogene Werkzeuge außerhalb von `scripts/`

| Einstieg | Eigentümer und Aufrufer | Entscheidung |
| --- | --- | --- |
| `backend.version` | Backend, Betreiber-CLI und Builds; Runtime, GoReleaser, Taskfile, Produkt- und Demo-Container | Vereint Runtime-Metadatenzugriff, Validierungsmodell und CLI-Export. Revision und optionaler Tag sind explizite CLI-Eingaben; Git und Tag-Zielprüfung liegen beim jeweiligen Aufrufer. |
| `brand/generate-assets.mjs` | Brand; `task brand:generate` und `task brand:check` | Ein einziger Einstieg erzeugt und prüft die tatsächlich ausgelieferten Derivate, Quellen, Tokens und Lizenzen. Die beiden früheren Brand-Skripte wurden nicht zusammenkopiert, sondern als ein gemeinsamer Vertrag mit einer Eigentümergrenze zusammengeführt. |
| `docs/media/check.py` | Dokumentation/Publikation; `task docs:media:check` | Prüft die von Playwright erzeugten PNG-Dateien und die dazugehörigen Fixture-/Viewport-Metadaten mit dem Standardwerkzeug `file`. Behalten als kleiner Medienvertrag; ein eigener PNG-Parser ist entfernt. |
| `docs/publication/` und `backend.fastapi_assembly` | Dokumentation/Publikation; `docs:publication*` und der Publication-Workflow | Eingechecktes Hugo-Projekt mit Blowfish-Modulpin; `docs/Taskfile.yml` bestimmt Ausgabe und Git-Metadaten einmal je Aufbau und führt Hugo, FastAPI-OpenAPI-Export, TypeDoc und Publikationsmetadaten aus. Browser-, Accessibility- und Linkprüfungen konsumieren dieselbe Artefaktausgabe und verlangen deren Metadatenmarker. Wiki-Inhalte bleiben im GitHub Wiki; die generische Linkprüfung bleibt beim Standardwerkzeug. |
| `scripts/run-pester.ps1` | OCI, Compose, Betreiber-CLI und Kompatibilität; Pester-Tasks | Installiert die gepinnte Pester-Version, erlaubt gezielte Dateiauswahl und erzeugt den standardisierten NUnit-Report. |

## Entfernte Einstiege

`check_brand_references.mjs`, `render_brand_review.mjs` und die historischen
Brand-Nachweise wurden mit #637 entfernt.
Der abgelöste Prototyp und sein Adapter wurden mit #638 entfernt.
Die einmalige Wiki-Migration und ihre Dauerverträge wurden mit #640 entfernt.
`compose-command.sh` und `validate-compose.sh` waren dünne Wrapper und sind
durch direkte, im Taskfile sichtbare Docker-Aufrufe ersetzt.
`check_demo_media.py` wurde nach `docs/media/check.py` verlagert und auf den
kleinen Metadatenvertrag mit dem Standardwerkzeug `file` reduziert.
`scripts/sbom.py` wurde mit #811 entfernt;
direkte gepinnte Syft-Aufrufe erzeugen ausschließlich die SBOMs der veröffentlichten OCI-Images.
`scripts/verify_cli_release.py` wurde mit #811 entfernt;
die heutige CLI-Reproduzierbarkeitsprüfung vergleicht zwei GoReleaser-Builds
gemäß Artefaktmanifest in `scripts/operator-reproducibility.ps1`.
`scripts/export_openapi.py` wurde mit #811 entfernt;
der direkt ausführbare kanonische FastAPI-Assembly-Einstieg erzeugt das
OpenAPI-Dokument für die Publikation.
Die Transporttypen stammen vor jedem Frontend-Build aus demselben
FastAPI-Checkout und werden von `openapi-ts` in sein konfiguriertes
Verzeichnis geschrieben.
Die Drift- und Dateiabgleichwrapper wurden mit #812 entfernt.
`scripts/check_documentation.py` wurde mit #948 entfernt.
`task docs` nutzt den strict MkDocs-Build für Navigationsziele und interne
Links samt Ankern; Seitenstruktur und ADR-Redaktion bleiben Gegenstand des
Reviews.
`scripts/build_metadata.py` ist mit #812 in `backend.version` aufgegangen;
Git-Aufrufe und Release-Tag-Zielprüfungen bleiben bei Aufrufern.
`scripts/validate_demo_url_contract.py` ist mit #812 in `demo.contract`
aufgegangen, das den Aufruf für manuelle Publikation bereitstellt.
