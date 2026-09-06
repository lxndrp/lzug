# Werkzeuginventar

Dieses Inventar hält für jeden ausführbaren Einstieg den aktuellen Eigentümer,
die direkten Aufrufer und den eigenständigen Vertrag fest.
Generische Format-, Link-, Build- und Testaufgaben bleiben bei den jeweiligen
Standardwerkzeugen.
Die Liste ist keine zweite Test- oder API-Dokumentation.

## Verbleibende repositoryweite Einstiegspunkte

| Einstieg | Eigentümer und direkte Aufrufer | Eigenständiger Vertrag und Entscheidung |
| --- | --- | --- |
| `scripts/build-frontend.sh` | Frontend; `frontend/package.json`, Dockerfiles | Staged die exakt benötigten Brand- und Build-Metadaten und ruft Angular mit der gewählten Konfiguration auf. Behalten, weil diese Assembly nicht durch `npm` oder Angular ausgedrückt wird. |
| `scripts/build_metadata.py` | Repository-/Buildgrenze; Dockerfiles, Taskfile, Demo- und Releaseabläufe | Liefert die fail-closed Identität aus Tag, Revision und Version für Backend, Frontend, OCI und CLI. Behalten als gemeinsam genutzten Produktmetadatenvertrag. |
| `scripts/check_documentation.py` | Dokumentation; `task docs:check` | Prüft nur den aktuellen Dokumentationsbaum, MkDocs-Navigation, ADR-Status, Handbuchbestand und Root-Grenzen. Link-, Markdown- und Buildprüfung verbleiben bei MkDocs/Hugo. |
| `scripts/compose-smoke.sh` | OCI/Self-Hosting; `task quality:compose` | Beweist den tatsächlich gestarteten Compose-Container, Restart, Stop/Start und `/data`-Persistenz. Behalten, weil `compose config` keinen Laufzeit- oder Wiederanlaufvertrag beweist. |
| `scripts/compose_policy.py` | OCI/Self-Hosting; `task quality:compose-config` und sein Vertragstest | Prüft lzug-spezifische Image-, Port-, Volume- und Secret-Grenzen nach der generischen Compose-Auswertung. Behalten; die Policy ist kein Standard-Compose-Schema. |
| `scripts/container-contract.sh` | OCI/Self-Hosting; Container-Smokes und lokale Image-Tasks | Kapselt ausschließlich die Docker/Podman-Auswahl, den gemeinsamen Health-/User-/Metadatenzugriff und die Bereinigung. Behalten, um dieselbe portable Lifecycle-Grenze nicht zu kopieren. |
| `scripts/container-smoke.sh` | OCI/Self-Hosting; `task quality:container` | Beweist HTTP-, Sicherheitsheader-, Authentifizierungs-, Scope- und Buildidentitätsgrenzen des Produktimages. Behalten als einziger vollständiger Produktimage-Smoke. |
| `scripts/demo-container-smoke.sh` | Öffentliche Demo; `task quality:demo` | Beweist den separaten App-/Seed-Containervertrag einschließlich Seed-Revision, Runtime-Policy und Wiederanlaufgrenzen. Behalten, weil der allgemeine Produktimage-Smoke diese Demo-Paarung nicht abdeckt. |
| `scripts/demo_deployment.py` | Demo-Delivery; Demo-Deploy-Workflow | Orchestriert die konfigurierte Azure-Revision, readiness, Smoke und Diagnostik mit fail-closed Identitätsprüfung. Behalten; OpenTofu und Azure CLI bilden diesen gebundenen Ablauf nicht als einen Vertrag ab. |
| `scripts/demo_snapshot.py` | Demo-Delivery; Snapshot-Workflow und Demo-Vertragstests | Validiert die reproduzierbare Snapshot-Identität und das Ablauf-/Resetfenster. Behalten als eigenständige Snapshot-Grenze. |
| `scripts/operator-container-smoke.sh` | Betreiber-CLI/OCI; `task quality:operator-container` | Beweist, dass die veröffentlichte CLI das gebaute Produktimage über das Admin-Protokoll sicher erreicht. Behalten; Go-Unit-Tests und der allgemeine Container-Smoke decken diese Grenze nicht gemeinsam ab. |
| `scripts/sbom.py` | Delivery/OCI; Quality-, PR- und Release-Workflows | Bindet Syft an die lzug-eigene CycloneDX-Identität, CLI-/Image-/Dependency-Quellen und die deterministische Release-Aggregation. Behalten, weil diese Lieferartefaktgrenze über Standard-SBOM-Erzeugung hinausgeht. |
| `scripts/validate_demo_url_contract.py` | Öffentliche Publikation; Publication-Workflow und Vertragstests | Erzwingt die erlaubte kanonische HTTPS-Origin ohne Credentials, Pfad oder fremde Demo-/Stage-Hosts. Behalten als Sicherheitsgrenze der konfigurierten Publikation. |
| `scripts/verify-demo-image-pair.sh` | Demo-Delivery; Promotion- und Snapshot-Workflows | Verifiziert vor einer Azure-Änderung die gemeinsame digest-, Tag-, Commit-, Schema- und Seed-Identität von App und Seed. Behalten als atomare Promotion-Grenze. |
| `scripts/verify_cli_release.py` | Betreiber-CLI; `task quality:operator` | Vergleicht zwei GoReleaser-Läufe einschließlich Archive, Metadaten und Lizenzen. Behalten als reproduzierbare Lieferprüfung, die GoReleaser allein nicht garantiert. |

## Komponentenbezogene Werkzeuge außerhalb von `scripts/`

| Einstieg | Eigentümer und Aufrufer | Entscheidung |
| --- | --- | --- |
| `brand/generate-assets.mjs` | Brand; `task brand:generate` und `task brand:check` | Ein einziger Einstieg erzeugt und prüft die tatsächlich ausgelieferten Derivate, Quellen, Tokens und Lizenzen. Die beiden früheren Brand-Skripte wurden nicht zusammenkopiert, sondern als ein gemeinsamer Vertrag mit einer Eigentümergrenze zusammengeführt. |
| `fixtures/generate.py` | Synthetische Fixtures; `task fixtures:check`, lokale Erzeugung | Erzeugt nur die noch aktiven SQL-, Angular- und Demo-Adapter aus der kanonischen JSON-Quelle. Der historische Prototyp-Adapter und seine Strukturprüfung sind entfernt. |
| `docs/media/check.py` | Dokumentation/Publikation; `task docs:media:check` | Prüft die von Playwright erzeugten PNG-Dateien und die dazugehörigen Fixture-/Viewport-Metadaten mit dem Standardwerkzeug `file`. Behalten als kleiner Medienvertrag; ein eigener PNG-Parser ist entfernt. |
| `docs/publication.py` | Dokumentation/Publikation; `task docs:publication*` und der Publication-Workflow | Montiert die produktiven Dokumentationsquellen und erzeugt den reproduzierbaren Hugo-/Relearn-Artifact. Generische Markdown-, Link- und Buildaufgaben bleiben beim Generator. |
| `tests/compatibility/v060-age-migration-smoke.sh` | Kompatibilitätstests; `task quality:operator-container` | Prüft den weiterhin unterstützten v0.6.0-Upgrade-/Restore-Pfad. Unter `tests/compatibility/` statt im allgemeinen Einstiegsordner, weil es kein tägliches Werkzeug und keine aktuelle Runtime-Orchestrierung ist. |

## Entfernte Einstiege

`check_brand_references.mjs`, `render_brand_review.mjs` und die historischen
Brand-Nachweise wurden mit #637 entfernt.
Der abgelöste Prototyp und sein Adapter wurden mit #638 entfernt.
Die einmalige Wiki-Migration und ihre Dauerverträge wurden mit #640 entfernt.
`compose-command.sh` und `validate-compose.sh` waren dünne Wrapper und sind
durch direkte, im Taskfile sichtbare Docker-/Podman-Aufrufe ersetzt.
`check_demo_media.py` wurde nach `docs/media/check.py` verlagert und auf den
kleinen Metadatenvertrag mit dem Standardwerkzeug `file` reduziert.
