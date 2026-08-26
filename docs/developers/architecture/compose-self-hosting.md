# Docker-Compose-Referenzinstallation

Die Referenzinstallation besteht aus einem einzigen `lzug`-Service und einem
benannten Volume für `/data`. Der Container läuft als UID/GID `10001:10001`,
mit schreibgeschütztem Root-Dateisystem, einem flüchtigen `/tmp`, ohne
Capabilities und standardmäßig nur auf `127.0.0.1`. Ein vorhandener Reverse
Proxy kann dadurch den Container erreichen; Compose veröffentlicht keinen
öffentlichen Listener und bringt bewusst keinen konkurrierenden Caddy mit.

## Voraussetzungen und Image-Vertrag

Docker Compose v2 oder ein äquivalenter Podman-Compose-Befehl wird benötigt.
Die Compose-Datei akzeptiert ausschließlich eine konkrete SemVer-Referenz wie
`ghcr.io/lxndrp/lzug:1.2.3` oder vorzugsweise den in den Releaseinformationen
ausgewiesenen Digest
`ghcr.io/lxndrp/lzug@sha256:<64 hexadezimale Zeichen>`. Die Beispielversion ist
durch eine tatsächlich veröffentlichte Version zu ersetzen. `latest` und
Platzhalter werden von der separat getesteten lzug-Policy in
`scripts/compose_policy.py` abgewiesen.

Solange noch kein öffentlicher Release existiert, bleibt `LZUG_IMAGE` in
`.env.example` bewusst leer. Der lokale Nachweis bleibt unverändert möglich:

```sh
cp .env.example .env
docker build --tag lzug:0.1.0-local --build-arg VCS_REF="$(git rev-parse HEAD)" .
sed -i.bak 's/^LZUG_IMAGE=.*/LZUG_IMAGE=lzug:0.1.0-local/' .env
rm .env.bak
```

Die lokale `0.1.0-local`-Markierung ist kein veröffentlichtes Release und
wird nicht als Pull-Erfolg ausgegeben. Für eine veröffentlichte Installation
setzt `.env` die echte SemVer- oder Digest-Referenz aus dem zugehörigen
[GitHub Release](../releases.md); Repository-Secrets gehören nicht in diese
Datei.

## Installation und Konfiguration

```sh
cp .env.example .env
# Beispielsweise LZUG_IMAGE=ghcr.io/lxndrp/lzug:1.2.3 oder ...@sha256:<digest>
docker compose config --quiet
scripts/validate-compose.sh
docker compose pull
docker compose up -d
```

`docker compose config --quiet` ist die verbindliche generische Prüfung für
Syntax, Variablenauflösung und Compose-Struktur. `scripts/validate-compose.sh`
rendert danach dasselbe Standardmodell und prüft ausschließlich die
lzug-Betriebsinvarianten: unveränderliches Image, Non-Root-/Read-only-Betrieb,
Capabilities, Socket- und Portgrenze, Persistenz, Healthcheck sowie die
sicherheitsrelevanten Runtime-Defaults. Trivy Config und Conftest werden hier
nicht zusätzlich eingeführt: Compose deckt die generische Struktur bereits ab,
und die kleine exakte Projektpolicy ist ohne weitere Toolabhängigkeit direkt
testbar.

Der Default-Port ist `127.0.0.1:8000`. Ein Reverse Proxy wird separat
konfiguriert und kann diesen lokalen Port weiterreichen. Für einen anderen
lokalen Port setzt `LZUG_HOST_PORT`; `LZUG_BIND_ADDRESS` sollte bei einem
externen Proxy auf `127.0.0.1` bleiben. Die vollständigen Runtime-Variablen
des Images sind in der [OCI-Runtime-Dokumentation](oci-runtime.md)
beschrieben; Compose setzt deren `/data`-Defaults:

| Variable                                                 | Compose-Default             | Zweck                                                                 |
| -------------------------------------------------------- | --------------------------- | --------------------------------------------------------------------- |
| `LZUG_IMAGE`                                             | erforderlich                | veröffentlichte SemVer- oder Digest-Referenz                          |
| `LZUG_BIND_ADDRESS`                                      | `127.0.0.1`                 | Host-Bind-Adresse des Ports                                           |
| `LZUG_HOST_PORT`                                         | `8000`                      | lokaler Host-Port des Reverse Proxy-Ziels                             |
| `LZUG_DATA_VOLUME`                                       | `lzug_data`                 | stabiler Name des persistenten Volumes                                |
| `LZUG_HOST`                                              | `0.0.0.0`                   | Container-Bind-Adresse                                                |
| `LZUG_PORT`                                              | `8000`                      | Container-Port und internes Healthcheck-Ziel                          |
| `LZUG_STATIC_DIR`                                        | `/app/frontend`             | Angular-Produktionsbundle                                             |
| `LZUG_HEALTHCHECK_URL`                                   | automatisch aus `LZUG_PORT` | Readiness-Endpunkt                                                    |
| `LZUG_HTTPS_ONLY`                                        | `true`                      | Secure-Cookies und HSTS hinter dem Reverse Proxy                      |
| `LZUG_CORS_ALLOWED_ORIGINS`                              | leer                        | same-origin; exakte optionale Origins                                 |
| `LZUG_SESSION_TTL_SECONDS`                               | `28800`                     | gemeinsame Cookie-/Server-Sessionlaufzeit                             |
| `LZUG_MAX_REQUEST_BYTES`                                 | `1048576`                   | maximales JSON-Request-Body                                           |
| `LZUG_AUTH_RATE_LIMIT` / `LZUG_AUTH_RATE_WINDOW_SECONDS` | `20` / `60`                 | öffentliches Auth-Limit je IP und Route                               |
| `LZUG_MAX_UPLOAD_BYTES`                                  | `10485760`                  | maximale Dokumentgröße                                                |
| `LZUG_ALLOWED_UPLOAD_MEDIA_TYPES`                        | PDF, JPEG, PNG, Text        | exakte Upload-Allowlist                                               |
| `LZUG_WEB_PUSH_VAPID_PRIVATE_KEY` / `LZUG_WEB_PUSH_SUBJECT` | leer                     | optionaler persistenter P-256-Schlüssel und VAPID-Kontakt             |
| `LZUG_EXTERNAL_URL`                                      | leer                        | authentifizierte Basis-URL für externe Verweise                        |
| `LZUG_SMTP_*`                                            | leer / Port `25`            | optionaler providerneutraler E-Mail-Fallback                           |
| `LZUG_NOTIFICATION_SINK`                                 | `false`                     | explizite Test-/Demo-Umleitung ohne Empfängerkontakt                   |
| `LZUG_DATA_DIR`                                          | `/data`                     | Wurzel des persistenten Datenvertrags                                 |
| `LZUG_DATABASE_PATH`                                     | `/data/lzug.sqlite`         | SQLite-Datei                                                          |
| `LZUG_DATABASE_URL`                                      | leer                        | alternative SQLite-Datei-URL; nicht zusammen mit `LZUG_DATABASE_PATH` |
| `LZUG_DOCUMENTS_PATH`                                    | `/data/documents`           | Dokumentenspeicher                                                    |
| `LZUG_BACKUPS_PATH`                                      | `/data/backups`             | Migrations-/Sicherungsablage                                          |

`LZUG_DATABASE_URL` und `LZUG_DATABASE_PATH` dürfen nicht gleichzeitig einen
Wert tragen. Es gibt keine Authentifizierungs-, Autorisierungs- oder
Migrations-Abkürzung; der Start führt nur die vorgesehenen Migrationen aus.
Die Anwendung startet ohne VAPID-Schlüssel und ohne SMTP-Relay; fachliche
Benachrichtigungen bleiben dann in lzug verfügbar. Die Kanal- und
Betreibergrenzen beschreibt die
[Benachrichtigungsarchitektur](notifications.md).

## Persistenz, Update und Diagnose

Vor dem Start verlangt die Anwendung auf jedem eindeutigen Dateisystem der
Persistenzpfade mindestens 64 MiB freien Speicher. Diese testgestützte Schwelle
ist nur ein fail-closed Startschutz, keine Kapazitätsempfehlung. Für CPU und RAM
existieren in `v0.1.0` weder Ressourcenlimits noch Lasttests; quantitative
Mindestwerte wären daher nicht belastbar. Die vollständige Abgrenzung steht in
den [Release- und Betriebsnachweisen für `v0.1.0`](../release-evidence-v0.1.0.md).

`lzug_data` bleibt bei `docker compose stop`, `start`, `restart`, `up` und
`down` erhalten. Ein neues Image ersetzt den Inhalt von `/data` nicht. Das
Volume darf nur mit ausdrücklicher Datenlöschung über `docker compose down
--volumes` entfernt werden. Den Wert von `LZUG_DATA_VOLUME` bei einer
Neuinstallation beibehalten, wenn die bestehende Datenbank weiterverwendet
werden soll.

Updates verwenden eine neue unveränderliche Referenz:

```sh
docker compose pull
docker compose up -d
docker compose ps
docker compose logs --tail=100 lzug
```

Der Container wird nur als `healthy` gemeldet, wenn `/api/health` HTTP 200 mit
`status: "ok"` liefert. Fehlende Datenbank, erforderliche Migrationen,
fehlende Schreibrechte oder zu wenig Speicher führen zu einer verständlichen
Start-/Readiness-Fehlermeldung und zu einem ungesunden Container. Diagnose:

```sh
docker compose ps
docker compose logs lzug
docker compose exec lzug python -m backend.healthcheck
```

`task quality:compose-config` führt die Standardvalidierung, die getrennte
lzug-Policy und deren Negativtests ohne Image-Build aus. Der vollständige
Runtime-Nachweis inklusive Health, Non-Root, Neustart, Stop/Start und
`/data`-Persistenz läuft mit einem vorhandenen Image über:

```sh
LZUG_IMAGE=lzug:0.1.0-local scripts/compose-smoke.sh
```

Podman verwendet für beide Ebenen äquivalent:

```sh
CONTAINER_ENGINE=podman task quality:compose-config
CONTAINER_ENGINE=podman LZUG_IMAGE=lzug:0.1.0-local scripts/compose-smoke.sh
```

Bei SELinux ist für Bind-Mounts der Kontext `:Z` erforderlich. Diese kanonische
Compose-Datei
verwendet absichtlich ein Volume, sodass kein Bind-Mount-Chown und kein
Host-Socket erforderlich sind. Fehlt `podman compose` oder ist die Engine
nicht erreichbar, wird der praktische Smoke-Test als Umgebungsgrenze mit
Rückgabecode `77` beendet; die Standardkonfiguration bleibt mit
`podman compose config --quiet` prüfbar.
