# OCI-Runtime

Das Repository liefert mit `Dockerfile` ein einzelnes OCI-Image für das
Angular-Frontend, das Python-Backend und die REST-API. Der Build verwendet
`frontend/package-lock.json` für den Frontend-Schritt und `uv.lock` für die
produktiven Python-Abhängigkeiten. Das Runtime-Image enthält nur das
kompilierte Browser-Bundle, die Backend-Quellen, Migrationen und die dafür
benötigten Python-Pakete; Tests, Demo-Seed, Dokumentation, Lockfiles,
Node.js/npm und uv sind nicht enthalten.

## Lokaler Build

```sh
revision="$(git rev-parse HEAD)"
identity="$(python3 scripts/build_metadata.py --revision "$revision" --field identity)"
docker build --tag lzug:local \
  --build-arg "BUILD_IDENTITY=$identity" \
  --build-arg "VCS_REF=$revision" .
```

Der Build benötigt eine laufende Docker- oder Podman-Engine sowie Zugriff auf
die jeweiligen Container-Registries für die ausdrücklich gepinnten
Build-Basen. `npm ci` und `uv sync --locked` brechen bei Abweichungen von den
Lockfiles ab. `task quality:oci` baut dasselbe Dockerfile als
`lzug:0.0.0-dev.local`; `task quality:overall` verwendet dieses Image für die
Container-, Compose- und Betreiber-CLI-Verträge. `task dev` und `task test`
bleiben davon getrennt.

## Docker- und Podman-Betrieb

Die Anwendung läuft standardmäßig als UID/GID `10001:10001`, lauscht auf
Port `8000` und verwendet ausschließlich `/data` für dauerhaften Zustand:

```sh
mkdir -p data
docker run --detach --name lzug \
  --publish 127.0.0.1:8000:8000 \
  --mount "type=bind,src=$PWD/data,dst=/data" \
  --read-only --tmpfs /tmp \
  lzug:local
```

Bei einem Bind-Mount muss `data/` für UID/GID `10001:10001` beschreibbar sein.
Alternativ kann Docker mit `--user 10001:10001` und Podman mit seinem
`--userns=keep-id`- beziehungsweise `:U`-Mechanismus an die lokale
Benutzer-ID angepasst werden. Podman verwendet bei SELinux-Systemen den
Mount-Zusatz `:Z`:

```sh
mkdir -p data
podman unshare chown -R 10001:10001 data
podman run --detach --name lzug \
  --publish 127.0.0.1:8000:8000 \
  --volume "$PWD/data:/data:Z" \
  --read-only --tmpfs /tmp \
  lzug:local
```

Das Image setzt `VOLUME /data`, ersetzt den Inhalt dieses Verzeichnisses
nicht und erzeugt beim Start Datenbank, `documents/` und `backups/` nur dort.
Der Startparameter `--init` führt die vorhandenen Migrationen aus; ein
unerwarteter oder nicht bereiter Datenbankstand verhindert den Serverstart.

Für einen automatisierten Smoke-Test gegen ein bereits gebautes Image dient
das portable Skript:

```sh
scripts/container-smoke.sh lzug:local
CONTAINER_ENGINE=podman scripts/container-smoke.sh lzug:local
```

Es prüft Engine-Verfügbarkeit, Readiness, API-Health, Root-/SPA-Auslieferung,
ein fehlendes Asset, einen Neustart und die erneute Readiness. Rückgabecode
`77` kennzeichnet ausschließlich eine fehlende oder nicht erreichbare lokale
Engine. Der Smoke-Test verwendet ein temporäres Container-Volume und räumt es
beim Beenden auf.

## Laufzeitkonfiguration und Sicherheitsgrenzen

Die Konfiguration erfolgt über CLI-Parameter oder Umgebungsvariablen. Die
wichtigsten Werte sind:

| Zweck               | CLI                     | Umgebungsvariable                                        | Standard                           |
| ------------------- | ----------------------- | -------------------------------------------------------- | ---------------------------------- |
| HTTP-Adresse        | `--host`                | `LZUG_HOST`                                              | `0.0.0.0` im Image                 |
| HTTP-Port           | `--port`                | `LZUG_PORT`                                              | `8000`                             |
| statische Ausgabe   | `--static-dir`          | `LZUG_STATIC_DIR`                                        | `/app/frontend` im Image           |
| Datenverzeichnis    | `--data-dir`            | `LZUG_DATA_DIR`                                          | `/data`                            |
| SQLite-Pfad/URL     | `--db`/`--database-url` | `LZUG_DATABASE_PATH`/`LZUG_DATABASE_URL`                 | `/data/lzug.sqlite`                |
| Dokumente           | `--documents`           | `LZUG_DOCUMENTS_PATH`                                    | `/data/documents`                  |
| Migration-Backups   | `--backups`             | `LZUG_BACKUPS_PATH`                                      | `/data/backups`                    |
| Healthcheck-URL     | —                       | `LZUG_HEALTHCHECK_URL`                                   | `http://127.0.0.1:8000/api/health` |
| HTTPS-/Cookie-Modus | —                       | `LZUG_HTTPS_ONLY`                                        | `true`                             |
| CORS-Allowlist      | —                       | `LZUG_CORS_ALLOWED_ORIGINS`                              | leer/same-origin                   |
| Sessionlaufzeit     | —                       | `LZUG_SESSION_TTL_SECONDS`                               | `28800`                            |
| JSON-Größenlimit    | —                       | `LZUG_MAX_REQUEST_BYTES`                                 | `1048576`                          |
| Auth-Rate-Limit     | —                       | `LZUG_AUTH_RATE_LIMIT` / `LZUG_AUTH_RATE_WINDOW_SECONDS` | `20` / `60`                        |
| Uploadgrenze        | —                       | `LZUG_MAX_UPLOAD_BYTES`                                  | `10485760`                         |
| Uploadtypen         | —                       | `LZUG_ALLOWED_UPLOAD_MEDIA_TYPES`                        | PDF, JPEG, PNG, Text               |

Secrets, Zugangsdaten, Umgebungswerte und Demo-Daten werden weder in den
Build-Stufen noch im Image festgelegt. Das Root-Dateisystem kann
schreibgeschützt betrieben werden; `/tmp` ist der einzige zusätzliche
flüchtige Schreibpfad. Der Prozess ist nicht privilegiert, verwirft keine
Anwendungssicherheitsregeln und beendet den HTTP-Server über einen
SIGTERM-/SIGINT-gesteuerten Shutdown-Pfad.

Der Build-Kontext ist über `.dockerignore` deny-by-default begrenzt. Das Image
enthält keine Git-Historie, `.env`-Dateien, Tests, Seed-Daten oder lokalen
Auth-Schlüssel. Ohne `LZUG_AUTH_ENCRYPTION_KEY` erzeugt die Anwendung den
Fernet-Schlüssel mit Modus 0600 im persistenten `/data`-Vertrag; er muss mit
dem Datenbestand gesichert werden und gehört nicht in Image oder Compose-Datei.

`/api`, `/api/health`, `/api/openapi.json` und `/api/docs` bleiben API-Routen;
nur Health ist ohne Session als GET-API öffentlich. Die erforderlichen
Login-/Aktivierungs-/Recovery-POST-Routen und sämtliche Schutzparameter sind
in der [Security-Baseline](security-baseline.md) inventarisiert.
Vorhandene Assets werden direkt ausgeliefert, fehlende Assets liefern 404 und
nur Routen ohne Dateisuffix erhalten den Angular-SPA-Fallback. Damit kann ein
Reverse Proxy später vor dem Container ergänzt werden, ohne dass dieser
Runtime-Schritt bereits Compose oder eine Proxy-Konfiguration vorwegnimmt.

Der OCI-Workflow baut das Image bei relevanten Pull Requests genau einmal und
übergibt das per SHA-256 abgesicherte Docker-Archiv an zwei getrennte Jobs.
Der Runtime-Job prüft Revision, Non-Root-Vertrag, Start, Health, API, SPA und
die gehärteten Isolationsgrenzen. Der Scan-Job erzeugt mit Syft aus demselben
Image die kanonische CycloneDX-Image-SBOM und daneben aus den locked
Python-/npm-/Go-Eingaben eine getrennte Dependency-SBOM für Release- und
Lizenzreview. Trivy blockiert weiterhin behebbare High-/Critical-Befunde. Der
content-addressed BuildKit-Cache beschleunigt Builds, ohne Lockfile- oder
Kontextänderungen zu übergehen; Pull Requests dürfen den gemeinsamen Cache nur
lesen, aktualisiert wird er ausschließlich auf dem geschützten Hauptbranch.
Ein abschließender Gate-Job fasst Klassifikation, Build, Runtime und Scan zu
einem stabilen verpflichtenden Pull-Request-Status zusammen. Veröffentlichung
und GHCR-Release bleiben dem getrennten, nur durch einen freigegebenen
SemVer-Tag startenden [Release-Prozess](../releases.md) vorbehalten. Dieser
prüft den erfolgreichen vollständigen `Quality`-Workflow der exakten
`master`-SHA, wiederholt keine Runtime- oder Security-Prüfungen und
veröffentlicht SemVer-, Major-, Major.Minor- und Commit-SHA-Tags auf denselben
Registry-Digest. Genau eine aggregierte CycloneDX-SBOM ist sichtbares
Release-Asset; Provenance sowie die detaillierte Image-SBOM werden über GitHub
Attestations an die ausgelieferten Digests gebunden. Ein
`latest`-Tag wird nicht erzeugt.
