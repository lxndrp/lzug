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
docker build --tag lzug:local --build-arg VCS_REF="$(git rev-parse HEAD)" .
```

Der Build benötigt eine laufende Docker- oder Podman-Engine sowie Zugriff auf
die jeweiligen Container-Registries für die ausdrücklich gepinnten
Build-Basen. `npm ci` und `uv sync --locked` brechen bei Abweichungen von den
Lockfiles ab. Die vorhandenen lokalen Entwicklungsabläufe mit `task dev`,
`task test` und `task quality` bleiben davon getrennt.

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

| Zweck | CLI | Umgebungsvariable | Standard |
| --- | --- | --- | --- |
| HTTP-Adresse | `--host` | `LZUG_HOST` | `0.0.0.0` im Image |
| HTTP-Port | `--port` | `LZUG_PORT` | `8000` |
| statische Ausgabe | `--static-dir` | `LZUG_STATIC_DIR` | `/app/frontend` im Image |
| Datenverzeichnis | `--data-dir` | `LZUG_DATA_DIR` | `/data` |
| SQLite-Pfad/URL | `--db`/`--database-url` | `LZUG_DATABASE_PATH`/`LZUG_DATABASE_URL` | `/data/lzug.sqlite` |
| Dokumente | `--documents` | `LZUG_DOCUMENTS_PATH` | `/data/documents` |
| Migration-Backups | `--backups` | `LZUG_BACKUPS_PATH` | `/data/backups` |
| Healthcheck-URL | — | `LZUG_HEALTHCHECK_URL` | `http://127.0.0.1:8000/api/health` |
| HTTPS-/Cookie-Modus | — | `LZUG_HTTPS_ONLY` | `true` |
| CORS-Allowlist | — | `LZUG_CORS_ALLOWED_ORIGINS` | leer/same-origin |
| Sessionlaufzeit | — | `LZUG_SESSION_TTL_SECONDS` | `28800` |
| JSON-Größenlimit | — | `LZUG_MAX_REQUEST_BYTES` | `1048576` |
| Auth-Rate-Limit | — | `LZUG_AUTH_RATE_LIMIT` / `LZUG_AUTH_RATE_WINDOW_SECONDS` | `20` / `60` |
| Uploadgrenze | — | `LZUG_MAX_UPLOAD_BYTES` | `10485760` |
| Uploadtypen | — | `LZUG_ALLOWED_UPLOAD_MEDIA_TYPES` | PDF, JPEG, PNG, Text |

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

Der Security-Workflow baut das Image, prüft den Non-Root-Vertrag, scannt es und
erzeugt das CycloneDX-SBOM. #121 integriert anschließend den vollständigen
Start-/Health-/SPA-Smoke als eigenen Pull-Request-CI-Job. Veröffentlichung und
GHCR-Release bleiben dem getrennten Release-Prozess vorbehalten.
