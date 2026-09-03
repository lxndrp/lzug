# Installation und Konfiguration

Die Referenzinstallation betreibt genau eine lzug-Instanz für genau einen
lokalen Betriebsbereich.
Sie verwendet das veröffentlichte OCI-Image, die zum selben Release gehörende
`compose.yaml` und die portable CLI `lzug-admin`.

## Voraussetzungen

- Docker mit Compose v2 oder Podman mit einem funktionsfähigen
  `podman compose`-Provider;
- ein dauerhaftes lokales Volume für `/data`;
- ein betreiberseitiger HTTPS-Reverse-Proxy für jeden Zugriff außerhalb des
  Hosts;
- ein veröffentlichtes lzug-Release für Betrieb und CLI;
- ein mit `lzug-admin recipient-key generate` erzeugtes und getrennt
  verwahrtes X25519-age-Schlüsselpaar, wenn vollständige Backups genutzt
  werden sollen.

Es gibt keine validierte Mindestgröße für CPU, Arbeitsspeicher oder Datenträger.
Planen Sie zusätzlich zum aktuellen Datenbestand Platz für Dokumente,
Migrationen, mindestens zwei vollständige Backups und temporäre
Restore-Artefakte ein.

## Release-Artefakte auswählen und prüfen

Wählen Sie ausschließlich eine Version, die auf der
[Release-Seite](https://github.com/lxndrp/lzug/releases) veröffentlicht ist.
Das folgende Beispiel zeigt das Namensschema mit `v0.5.0`; für die in den
weiteren Seiten beschriebenen Betriebsbefehle ist mindestens `v0.6.0`
erforderlich.

```sh
VERSION=0.5.0
OS=linux
ARCH=amd64

curl -fsSLo compose.yaml \
  "https://raw.githubusercontent.com/lxndrp/lzug/v${VERSION}/compose.yaml"
curl -fLO \
  "https://github.com/lxndrp/lzug/releases/download/v${VERSION}/lzug-admin-${VERSION}-${OS}-${ARCH}.tar.gz"
sha256sum "lzug-admin-${VERSION}-${OS}-${ARCH}.tar.gz"
```

Vergleichen Sie den SHA-256-Wert vor dem Entpacken mit dem Digest des Assets auf
der Release-Seite.
Mit der GitHub CLI lässt sich derselbe veröffentlichte Wert maschinenlesbar
anzeigen:

```sh
gh release view "v${VERSION}" --repo lxndrp/lzug --json assets \
  --jq '.assets[] | [.name, .digest] | @tsv'
```

Für Windows stehen ZIP-Archive bereit; Linux und macOS verwenden `tar.gz`.
Installieren Sie genau das Archiv für Betriebssystem und Architektur und prüfen
Sie danach die eingebettete Release-Identität:

```sh
tar -xzf "lzug-admin-${VERSION}-${OS}-${ARCH}.tar.gz"
./lzug-admin --version
./lzug-admin --build-metadata
```

Die gemeldete Version, der Tag und die Revision müssen zum gewählten Release
gehören.
Die [Releaseautomation](https://github.com/lxndrp/lzug/blob/master/.github/workflows/release.yml)
veröffentlicht OCI-Image, sechs CLI-Archive, SBOM und Attestations aus derselben
geprüften Revision.

## Referenzkonfiguration

`compose.yaml` liest die folgenden Werte beim Erzeugen des Containers.
Jede Änderung wird erst durch erneutes `docker compose up -d` beziehungsweise
`podman compose up -d` wirksam; ein bloßer Prozessneustart übernimmt geänderte
Umgebungswerte nicht zuverlässig.

| Variable | Standard und Pflichtstatus | Geheimhaltungsbedarf | Wirkung beim erneuten `up -d` |
| --- | --- | --- | --- |
| `LZUG_IMAGE` | kein Standard, **Pflicht**; veröffentlichter SemVer-Tag oder Digest | nein | zieht und aktiviert das gewählte Image |
| `LZUG_BIND_ADDRESS` | `127.0.0.1`, optional | nein | ändert die Host-Bindung; öffentlich nur hinter TLS-Proxy binden |
| `LZUG_HOST_PORT` | `8000`, optional | nein | ändert den Host-Port |
| `LZUG_DATA_VOLUME` | `lzug_data`, optional | nein | wählt ein anderes Volume; Daten werden nicht automatisch übertragen |
| `LZUG_HOST` / `LZUG_PORT` | `0.0.0.0` / `8000`, optional | nein | ändert die interne Listener-Adresse beziehungsweise den Container-Port |
| `LZUG_STATIC_DIR` | `/app/frontend`, optional | nein | ändert den Pfad der ausgelieferten Oberfläche |
| `LZUG_DATA_DIR` | in Compose fest `/data` | nein | nicht von der Referenz abweichend konfigurieren |
| `LZUG_DATABASE_PATH` | `/data/lzug.sqlite`, optional | enthält gegebenenfalls sensible Pfadinformationen | wählt die SQLite-Datei; keine automatische Datenübertragung |
| `LZUG_DATABASE_URL` | leer, optional; nicht gemeinsam mit `LZUG_DATABASE_PATH` setzen | **ja**, falls die URL Zugangsdaten enthält | wählt die Datenbank-URL; keine automatische Datenübertragung |
| `LZUG_DOCUMENTS_PATH` | `/data/documents`, optional | enthält gegebenenfalls sensible Pfadinformationen | wählt den Dokumentpfad; keine automatische Datenübertragung |
| `LZUG_BACKUPS_PATH` | `/data/backups`, optional | enthält gegebenenfalls sensible Pfadinformationen | wählt den Artefaktpfad; keine automatische Datenübertragung |
| `LZUG_BACKUP_RECIPIENT_PUBLIC_KEY` | leer, nur Übergang von v0.6.x | nein, nur öffentlicher X25519-Schlüssel | wird beim Upgrade einmalig in die auditierte Empfängerkonfiguration übernommen; ab v0.7.0 `backup recipient set|replace` verwenden |
| `LZUG_REQUIRED_EXTERNAL_CONFIG` | leer, optional; kommaseparierte `LZUG_*`-Namen | nein, Werte dürfen hier nicht stehen | bestimmt die Readiness nach Restore |
| `LZUG_HEALTHCHECK_URL` | `http://127.0.0.1:8000/api/health`, optional | nein | ändert nur den internen Loopback-Healthcheck |
| `LZUG_HTTPS_ONLY` | `true`, optional | nein | steuert sichere Session-Cookies; für HTTPS-Betrieb `true` lassen |
| `LZUG_CORS_ALLOWED_ORIGINS` | leer und damit same-origin, optional | nein | erlaubt nur ausdrücklich genannte exakte HTTP(S)-Origins |
| `LZUG_SESSION_TTL_SECONDS` | `28800`, optional | nein | ändert die Laufzeit neuer Sessions |
| `LZUG_MAX_REQUEST_BYTES` | `1048576`, optional | nein | ändert das JSON-Request-Limit |
| `LZUG_AUTH_RATE_LIMIT` / `LZUG_AUTH_RATE_WINDOW_SECONDS` | `20` / `60`, optional | nein | ändert die HTTP-Authentifizierungsdrosselung |
| `LZUG_MAX_UPLOAD_BYTES` | `10485760`, optional | nein | ändert das Dokumentlimit; Proxy-Limit darauf abstimmen |
| `LZUG_ALLOWED_UPLOAD_MEDIA_TYPES` | PDF, JPEG, PNG und Text, optional | nein | ersetzt die erlaubte exakte Medientyp-Liste |
| `LZUG_NOTIFICATION_SINK` | `false`, optional | nein | aktiviert internen beziehungsweise Operator-Sink |
| `LZUG_EXTERNAL_URL` | leer, für Links und Push-Betrieb erforderlich | nein | setzt die exakte öffentliche HTTP(S)-Origin |
| `LZUG_WEB_PUSH_VAPID_PRIVATE_KEY` | leer, optional; nur gemeinsam mit `LZUG_WEB_PUSH_SUBJECT` | **ja** | aktiviert Web Push |
| `LZUG_WEB_PUSH_SUBJECT` | leer, optional; nur gemeinsam mit VAPID-Schlüssel | nein | setzt den Web-Push-Kontakt |
| `LZUG_SMTP_HOST` / `LZUG_SMTP_PORT` | leer / `25`, optional | Host nein | aktiviert E-Mail-Zustellung und wählt den Port |
| `LZUG_SMTP_FROM` / `LZUG_SMTP_STARTTLS` | leer / `false`, optional | Absender nein | setzt Absender und Transportmodus |
| `LZUG_SMTP_USERNAME` / `LZUG_SMTP_PASSWORD` | leer, optional | **ja** | setzt SMTP-Zugangsdaten |

Bewahren Sie Secrets nicht im Repository, in Shell-Historien oder in
weltlesbaren `.env`-Dateien auf.
Die Referenz-Compose-Datei übergibt Provider-Secrets als Umgebungsvariablen und
enthält noch keine eigene Secret-Store-Integration.
Nutzen Sie deshalb den geschützten Secret-Mechanismus des Hostbetriebs und
beschränken Sie Zugriff auf Engine, Servicekonfiguration und Container-Metadaten.

Der anwendungseigene Authentifizierungsschlüssel entsteht beim ersten Start als
`/data/.lzug-auth.key` mit Modus `0600` und gehört später in das geschützte
vollständige Backup.
Setzen oder ersetzen Sie ihn nicht manuell in einer bestehenden Instanz.

## Start und Diagnose

Setzen Sie mindestens das Image und starten Sie die Referenzinstallation:

```sh
ENGINE=docker
export LZUG_IMAGE="ghcr.io/lxndrp/lzug:${VERSION}"
export LZUG_EXTERNAL_URL="https://lzug.example.org"

"$ENGINE" compose -f compose.yaml pull
"$ENGINE" compose -f compose.yaml up -d
"$ENGINE" compose -f compose.yaml ps
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
```

Für Podman setzen Sie `ENGINE=podman`.
Ermitteln Sie den tatsächlichen Compose-Containernamen und führen Sie die
geheimnisfreie lokale Diagnose aus:

```sh
CONTAINER_ID="$("$ENGINE" compose -f compose.yaml ps -q lzug)"
CONTAINER="$("$ENGINE" inspect --format '{{.Name}}' "$CONTAINER_ID")"
CONTAINER="${CONTAINER#/}"

./lzug-admin --engine "$ENGINE" --container "$CONTAINER" status
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" config
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" doctor
```

Exit `0` bedeutet betriebsbereit, `30` eine vollständig ausgeführte Diagnose
mit Warnung und `31` mindestens einen Betriebsfehler.
`/api/health` ist nur Liveness; erst `/api/ready` und `doctor` prüfen den
Anwendungs-, Schema-, Konfigurations- und Persistenzzustand ausreichend für die
Inbetriebnahme.

## Erstes Betreiberkonto

Erzeugen Sie auf einer noch kontenlosen Instanz genau einmal eine Einladung:

```sh
./lzug-admin --engine "$ENGINE" --container "$CONTAINER" \
  bootstrap --email betreiber@example.org
```

Die Ausgabe enthält das Einladungstoken genau einmal.
Öffnen Sie anschließend `https://lzug.example.org/activate`, setzen Sie ein
Kennwort mit mindestens zwölf Zeichen, richten Sie TOTP ein und verwahren Sie
die einmalig angezeigten Recovery-Codes getrennt.
Ein Betreiberkonto besitzt dadurch noch keine fachliche Ausschussrolle.

## Reverse Proxy und TLS

Lassen Sie `LZUG_BIND_ADDRESS=127.0.0.1` und `LZUG_HTTPS_ONLY=true`, wenn ein
Reverse Proxy auf demselben Host terminiert.
Der Proxy muss ausschließlich den HTTP-Anwendungsport veröffentlichen, gültiges
TLS bereitstellen, WebSocket- oder Admin-Sonderrouten weder erfinden noch
freigeben und sein Request-Limit mindestens mit `LZUG_MAX_UPLOAD_BYTES`
abgleichen.
Setzen Sie `LZUG_EXTERNAL_URL` auf die exakte öffentliche HTTPS-Origin.
Bei reinem same-origin-Betrieb bleibt `LZUG_CORS_ALLOWED_ORIGINS` leer.

Der Container stellt selbst kein TLS bereit.
Engine-Socket, `/data`, Betreiber-CLI und der lokale Python-Adminprozess dürfen
niemals über den Reverse Proxy erreichbar sein.
