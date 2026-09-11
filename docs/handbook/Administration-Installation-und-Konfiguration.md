# Installation und Konfiguration

Die Referenzinstallation betreibt genau eine lzug-Instanz für genau einen
lokalen Betriebsbereich.
Sie verwendet das veröffentlichte OCI-Image, die zum selben Release gehörende
`compose.yaml` und die portable CLI `lzug-admin`.

## Voraussetzungen

- Docker Engine auf Linux mit Compose v2;
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
Jede Änderung wird erst durch erneutes `docker compose up -d` wirksam;
ein bloßer Prozessneustart übernimmt geänderte Umgebungswerte nicht zuverlässig.

| Variable | Standard und Pflichtstatus | Geheimhaltungsbedarf | Wirkung beim erneuten `up -d` |
| --- | --- | --- | --- |
| `LZUG_IMAGE` | kein Standard, **Pflicht**; exakte veröffentlichte SemVer-Version | nein | zieht und aktiviert das gewählte Image |
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
| `LZUG_WEB_PUSH_VAPID_PRIVATE_KEY` | leer, optional; nur gemeinsam mit `LZUG_WEB_PUSH_SUBJECT` | **ja** | aktiviert Web Push mit dem bestehenden VAPID-Schlüssel |
| `LZUG_WEB_PUSH_SUBJECT` | leer, optional; nur gemeinsam mit VAPID-Schlüssel | nein | setzt den Web-Push-Kontakt |
| `LZUG_SMTP_HOST` / `LZUG_SMTP_PORT` | leer / `25`, optional | Host nein | aktiviert E-Mail-Zustellung und wählt den Port |
| `LZUG_SMTP_FROM` / `LZUG_SMTP_STARTTLS` | leer / `false`, optional | Absender nein | setzt Absender und Transportmodus |
| `LZUG_SMTP_USERNAME` / `LZUG_SMTP_PASSWORD` | leer, optional | **ja** | setzt SMTP-Zugangsdaten |

VAPID und der Web-Push-Versand werden durch `pywebpush` umgesetzt.
Bestehende P-256-PEM-Schlüssel und registrierte Push-Endpunkte bleiben unverändert verwendbar.

Bewahren Sie Secrets nicht im Repository, in Shell-Historien oder in
weltlesbaren `.env`-Dateien auf.
Die Referenz-Compose-Datei übergibt Provider-Secrets als Umgebungsvariablen und
enthält noch keine eigene Secret-Store-Integration.
Nutzen Sie deshalb den geschützten Secret-Mechanismus des Hostbetriebs und
beschränken Sie Zugriff auf Docker, Servicekonfiguration und Container-Metadaten.

Der anwendungseigene Authentifizierungsschlüssel entsteht beim ersten Start als
`/data/.lzug-auth.key` mit Modus `0600` und gehört später in das geschützte
vollständige Backup.
Setzen oder ersetzen Sie ihn nicht manuell in einer bestehenden Instanz.

## Start und Diagnose

Setzen Sie mindestens das Image und starten Sie die Referenzinstallation:

```sh
export LZUG_IMAGE="ghcr.io/lxndrp/lzug-app:${VERSION}"
export LZUG_EXTERNAL_URL="https://lzug.example.org"

docker compose -f compose.yaml pull
docker compose -f compose.yaml up -d
docker compose -f compose.yaml ps
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/ready
```

Ermitteln Sie den tatsächlichen Compose-Containernamen und führen Sie die
geheimnisfreie lokale Diagnose aus:

```sh
CONTAINER_ID="$(docker compose -f compose.yaml ps -q lzug)"
CONTAINER="$(docker inspect --format '{{.Name}}' "$CONTAINER_ID")"
CONTAINER="${CONTAINER#/}"

./lzug-admin --container "$CONTAINER" status
./lzug-admin --container "$CONTAINER" config
./lzug-admin --container "$CONTAINER" doctor
```

Exit `0` bedeutet betriebsbereit, `30` eine vollständig ausgeführte Diagnose
mit Warnung und `31` mindestens einen Betriebsfehler.
`/api/health` ist nur Liveness; erst `/api/ready` und `doctor` prüfen den
Anwendungs-, Schema-, Konfigurations- und Persistenzzustand ausreichend für die
Inbetriebnahme.

## Lifecycle und Wartungsanzeige

Ein lebender Prozess ist nicht automatisch einsatzbereit.
`/api/health` bestätigt ausschließlich, dass HTTP antwortet, auch während
Initialisierung, Wartung, Migration oder eines diagnostizierbaren Fehlers.
`/api/ready` liefert HTTP 200 ausschließlich bei `state: ready` und `ready: true`;
alle anderen Zustände ergeben HTTP 503.
`/api/lifecycle` bleibt mit HTTP 200 zur öffentlichen Statusprüfung erreichbar.

| Öffentlicher Zustand | Bedeutung und nächster Schritt |
| --- | --- |
| `initializing` | Die Instanz wird geprüft und vorbereitet; Abschluss abwarten. |
| `ready` | Fachliche Anfragen sind freigegeben. |
| `maintenance` | Ein bewusst gestarteter Wartungsauftrag sperrt Fachanfragen; Auftragsstatus prüfen. |
| `migration_required` | Das Schema benötigt eine Aktualisierung; Status und unterstützten Freigabeweg prüfen. |
| `migrating` | Die Datenaktualisierung läuft; weder erneut starten noch den Prozess ersetzen. |
| `error` | Initialisierung, Prüfung oder Auftrag fehlgeschlagen; Diagnose und Wiederherstellungsweg prüfen. |
| `stopping`, `stopped` | Fachzulassung geschlossen; Prozessende beziehungsweise Wiederanlauf abwarten. |

Fachliche HTTP-Anfragen werden außerhalb von ready mit einem einheitlichen 503
und `error.code: runtime_not_ready` abgewiesen.
Die Antwort nennt nur den öffentlichen Zustand, keine Schema-, Datenbank-,
Pfad-, Secret- oder internen Fehlerdetails.
Ein bereits gesendeter Änderungsauftrag darf nicht blind wiederholt werden.
Die Weboberfläche zeigt einen zugänglichen Hinweis und eine manuelle
Statusprüfung mit Prüfzeitpunkt; es gibt keine automatische Polling- oder
Wiederholungsschleife.
Die Shell und ihre statischen Dateien bleiben erreichbar.

Betreiber verwenden `lzug-admin system status` beziehungsweise
`lzug-admin system doctor` für die autoritative Diagnose mit Ursache und
gegebenenfalls Auftrags-ID.
Der Socketanschluss und die Migrationsfreigabe werden mit den zugehörigen
Admintransport- und Upgradeverträgen bereitgestellt; die Wartungsanzeige
genehmigt selbst keine Migration.
Bis zur Umstellung bleibt der dokumentierte
[Update- und Wiederherstellungsweg](Administration-Update-und-Rollback.md)
maßgeblich; `--init` bleibt eine ausdrücklich angeforderte Startmigration.
Ohne diesen Auftrag wartet ein migrationsbedürftiger Prozess live und not-ready.
Ein fehlgeschlagener oder unterbrochener exklusiver Auftrag hält auch nach
Neustart die Fachzulassung geschlossen, bis eine geprüfte Wiederherstellung gelingt.

Docker- und Compose-Healthchecks prüfen ausschließlich Liveness.
Für die Inbetriebnahme und Deploymentabnahme wird Readiness zusätzlich geprüft.
Ein Reverse Proxy muss die Wartungs-Shell sowie die öffentlichen Probes auch
bei negativer Anwendungs-Readiness zum lebenden Prozess durchlassen.
Die Azure-Demo verwendet deshalb eine TCP-Probe für die plattformseitige
Verkehrsfreigabe und HTTP-Liveness für die Prozessüberwachung.
Promotion und Reset prüfen weiterhin ausdrücklich `/api/ready`, bevor sie
Anwendungsbereitschaft melden.
Die Plattformfreigabe allein ist kein erfolgreicher Deploymentnachweis.
Die [Azure-Probe-Semantik](https://learn.microsoft.com/en-us/azure/container-apps/health-probes)
unterscheidet diese Verkehrsfreigabe von der Liveness-Prüfung.

## Erstes Betreiberkonto

Erzeugen Sie auf einer noch kontenlosen Instanz genau einmal eine Einladung:

```sh
./lzug-admin --container "$CONTAINER" \
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

`LZUG_MAX_REQUEST_BYTES` begrenzt die tatsächlich eingelesenen Requestdaten
auch ohne verlässliches `Content-Length`.
Zu große Längenangaben werden vor dem Lesen abgewiesen;
beim Überschreiten während des Einlesens antwortet die Anwendung mit `413`
und liest den restlichen Body nicht weiter.
Bodylose Pfade puffern keine Requestdaten.
Der Anwendungspuffer hält höchstens das konfigurierte Limit;
der jeweils vom ASGI-Server gelieferte Chunk und dessen Transportpuffer
kommen hinzu und werden nicht durch dieses Limit dimensioniert.
Uvicorn begrenzt vorgelagertes Einlesen über seine Flusskontrolle und liest
nach einer abgeschlossenen Antwort den restlichen Request nicht für die
Anwendung ein.
Der Proxy muss eigene Größen- und Zeitlimits setzen und gültiges
HTTP-Framing an Uvicorn weitergeben.
`Transfer-Encoding` wird von lzug weiterhin mit `400` abgewiesen;
der Proxy muss Chunked-Requests entsprechend aufbereiten.
Siehe [Uvicorn-Serververhalten](https://github.com/Kludex/uvicorn/blob/0.52.4/docs/server-behavior.md)
und [ASGI-Requestereignisse](https://asgi.readthedocs.io/en/stable/specs/www.html#request-receive-event).

Der Container stellt selbst kein TLS bereit.
Docker-Socket, `/data`, Betreiber-CLI und der lokale Python-Adminprozess dürfen
niemals über den Reverse Proxy erreichbar sein.

## Socketzugriff

Die CLI verwendet einen bereits bereitgestellten lokalen Socket-Endpunkt.
Client und Backend sprechen darüber denselben versionierten Adminvertrag.
Bereitstellung und mögliche entfernte Weiterleitung liegen beim Betreiber;
der Anwendungsvertrag und die Tests enden am Socket.

Ein nicht geheimes Zielprofil lautet beispielsweise:

```json
{
  "endpoint": "unix:///run/lzug-admin/admin.sock",
  "target-name": "lzug-production"
}
```

`--config admin.json` wählt dieses Profil für direkte Commands oder `cli` aus.
Explizite Optionen haben Vorrang vor Umgebung und Konfigurationsdatei.
`target-name` ist ein optionaler Anzeigename, kein Identitätsnachweis.
Das Profil darf nicht zugleich einen Container auswählen.
Die [CLI-Referenz](https://github.com/lxndrp/lzug/blob/master/docs/developers/reference/cli.md)
beschreibt die Commands und Optionen.

Linux und macOS unterstützen einen absoluten Unix-Socketpfad.
Auf allen drei Bedienplattformen einschließlich Windows kann ein vorhandener
lokaler TCP-Socket mit `tcp://127.0.0.1:PORT` oder `tcp://[::1]:PORT` verwendet werden.
DNS-Namen, Wildcard- und entfernte TCP-Adressen werden abgewiesen.
Die CLI erstellt keinen Listener.
Ein Loopback-Port ist auch für andere lokale Prozesse erreichbar;
die Zugriffsbeschränkung des bereitgestellten Endpunkts liegt beim Betreiber.
Der Backend-Adminsocket bleibt ein Unix-Domain-Socket auf Linux.

Vor destruktiven Vorgängen zeigt die CLI den Zielnamen und den lokalen Endpunkt an.
Jeder Auftrag öffnet eine eigene Verbindung und prüft den Admin-Handshake,
bevor fachliche Daten übertragen werden.
Eine interaktive Sitzung hält das Ziel bis zum ausdrücklichen Zielwechsel stabil.
Bei Erfolg, Fehler, Abbruch oder Timeout schließt die CLI nur ihre Verbindung;
der bereitgestellte Listener und Socketpfad bleiben unverändert.
Aufträge werden nicht automatisch wiederholt.

`connection_failed` kennzeichnet einen fehlgeschlagenen Verbindungsaufbau;
`handshake_failed` eine fehlende gültige Adminantwort und
`version_incompatible` einen inkompatiblen Vertrag.
Ursachen unterhalb der Socket-Schnittstelle müssen mit den jeweiligen
Betriebsmitteln diagnostiziert werden.
Nach möglichem Ausführungsbeginn bleiben Auftrags- und Korrelations-ID sowie
`outcome_unknown` für die Zuordnung zu Audit und Auftragsstatus erhalten.
Prüfen Sie den Zustand vor einer erneuten Mutation.
Private Backup-/Restore-/Exportschlüssel verbleiben beim lokalen age-Schritt.

Die vollständige Image-/Compose-Umstellung folgt in #747;
die Migrations- und Releasefreigabe bleibt #272 zugeordnet.
Für veröffentlichte Installationen sind die verfügbaren Release-Artefakte maßgeblich.

### Beispiel: externe Weiterleitung mit SSH

Dieses Beispiel zeigt eine mögliche Bereitstellung des Sockets.
Es begründet kein Support- oder Testversprechen für SSH oder den entfernten Transport.
Der SSH-Dienst läuft auf dem Linux-Containerhost.
Ein Bind-Mount des dedizierten Laufzeitverzeichnisses macht den vom Backend
angelegten Socket auch auf dem Host zugänglich.
Das ganze Verzeichnis bleibt eingebunden, wenn das Backend den Socket neu erzeugt.
Bei User-Namespace-Remapping müssen die tatsächlich abgebildeten numerischen IDs
zur Eigentümer- und Peer-Prüfung des Backends passen.
Das verbindende SSH-Konto benötigt dieselbe Server-UID oder die konfigurierte
primäre Betreiber-GID; eine zusätzliche Gruppenzugehörigkeit genügt nicht.
Hinzu kommen die Zugriffsrechte des Socketpfads und seiner Verzeichnisse.
Die Anforderungen beschreibt der
[Socketvertrag](https://github.com/lxndrp/lzug/blob/master/docs/developers/components.md#backend).

Der Betreiber richtet Hostvertrauen, Authentisierung und erlaubte
Streamlocal-Weiterleitungen in OpenSSH ein.
Unter Linux/macOS kann er in einem eigenen Terminal beispielsweise ausführen:

```console
mkdir -m 700 /tmp/lzug-tunnel
ssh -N -T -o ExitOnForwardFailure=yes -L /tmp/lzug-tunnel/admin.sock:/run/lzug-admin/admin.sock lzug-production
```

Danach verwendet die CLI `--endpoint unix:///tmp/lzug-tunnel/admin.sock`.
OpenSSH stellt die Verbindung zum entfernten Socket her;
ein dortiger Admin-Netzwerkport oder eine entfernte CLI sind dafür nicht erforderlich.
Beenden und Bereinigen der Weiterleitung bleiben Aufgabe des Betreibers.
Details zu [OpenSSH-Weiterleitungen](https://man.openbsd.org/ssh.1#L) und
[Docker-Bind-Mounts](https://docs.docker.com/engine/storage/bind-mounts/)
stehen in der jeweiligen Betriebsdokumentation.
