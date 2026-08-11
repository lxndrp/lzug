# Betreiber-CLI für Authentifizierung

Die portable Go-CLI `lzug-admin` ist eine lokale Betriebsgrenze. Sie öffnet
keinen Netzwerk-Endpunkt und kennt weder SQLite noch SQLAlchemy. Für jede
Operation ruft sie das explizit benannte laufende Docker- oder Podman-Container-
Objekt mit einzelnen Argumenten auf:

```text
lzug-admin --container <name> <command> [options]
  -> <engine> exec --interactive <name> python -m backend.admin --protocol 1
```

Der Containername wird gegen eine strikte Zeichenmenge geprüft. Es gibt keine
Shell-Stringverkettung, keine Compose-Namensauflösung und keinen vom Benutzer
kontrollierten Befehl. Ohne `--engine` wird zuerst Docker, danach Podman über
`PATH` gesucht; ein gefundenes, aber nicht erreichbares Engine-Daemon bleibt
als Betriebsfehler sichtbar.

## Versionierter Vertrag

Die Go-CLI sendet genau ein UTF-8-JSON-Objekt über stdin und leitet stdout und
stderr des Python-Prozesses byteweise weiter. Python antwortet mit genau einem
JSON-Objekt und einer stabilen Prozesskennung:

```json
{
  "version": 1,
  "command": "invite",
  "arguments": {"email": "mitglied@example.invalid"}
}
```

Erfolgreiche Antworten haben `{"version":1,"ok":true,"result":{...}}`.
Fehler haben `{"version":1,"ok":false,"error":{"class":"...","message":"..."}}`.
Tokenwerte erscheinen ausschließlich im `result.token` einer erfolgreichen
einmaligen Ausgabe von `bootstrap`, `invite` oder `recover`. Fehlertexte,
Diagnosen und Requestdaten spiegeln keine Token zurück.

| Exit-Code | Fehlerklasse | Bedeutung |
| ---: | --- | --- |
| 0 | — | erfolgreich |
| 2 | `invalid_request` | CLI-Argumente ungültig |
| 10 | `engine_unavailable` | Docker/Podman nicht auffindbar |
| 11 | `engine_invocation_failed` | Engine konnte nicht gestartet werden |
| 20 | `invalid_request` | JSON oder Protokoll ungültig |
| 21 | `database_not_ready` | Migration/Readiness nicht bereit |
| 22 | `bootstrap_not_empty` / `account_exists` | kontrollierter Konflikt |
| 23 | `account_not_found` | Konto nicht vorhanden oder nicht aktiv |
| 24 | `token_invalid` | Token ungültig, abgelaufen oder verbraucht |
| 25 | `persistence_error` | kontrollierter Persistenzfehler |
| 70 | `internal_error` | unerwarteter Fehler, fail-closed |

## Befehle und Sicherheitsgrenzen

- `bootstrap --email <email>` erstellt nur auf einer Datenbank ohne Konto das
  erste aktive Betreiberkonto. Es ist nicht mit `person` oder einer
  Ausschussmitgliedschaft verbunden und gibt eine 24 Stunden gültige
  Einladung einmalig aus.
- `invite --email <email>` erstellt ein nicht-operatives Konto und eine
  24-Stunden-Einladung.
- `disable --account-id <id>` sperrt das Konto und widerruft seine aktiven
  Sessions in derselben Transaktion.
- `recover (--account-id <id> | --email <email>)` löst für ein aktives Konto
  einen 30 Minuten gültigen Recovery-Token aus.

Token werden mit kryptografisch zufälligem Material erzeugt und ausschließlich
als SHA-256-Prüfwert in `auth_token` gespeichert. Der interne Python-Service
markiert die Werte beim Verbrauch atomar als verbraucht; Ablauf und Wiederholung
werden identisch abgewiesen. `consume-invitation` und `consume-recovery` lesen
einen Token ausschließlich aus stdin und sind für Integrations- und spätere
Auth-Flows vorgesehen.

Kennwort, Argon2id, TOTP und Recovery-Codes gehören weiterhin nicht zum
Betreiber-CLI-Vertrag #269. #266 verwendet die dort ausgegebenen Einladungs-
und Betreiber-Recovery-Token ausschließlich über die öffentlichen lokalen
Auth-Flows und erweitert die CLI nicht. Recovery-Codes sind davon strikt
getrennte Mitgliedsgeheimnisse: Sie werden niemals von der CLI erzeugt oder
ausgegeben. Passkeys und OIDC bleiben die getrennten Folgearbeiten #267 und
#268.

## Builds und lokale Prüfung

Die CLI wird unabhängig vom OCI-Image gebaut:

```sh
go test ./...
go build -trimpath ./cmd/lzug-admin
GOOS=linux GOARCH=amd64 go build -trimpath ./cmd/lzug-admin
GOOS=darwin GOARCH=amd64 go build -trimpath ./cmd/lzug-admin
GOOS=windows GOARCH=amd64 go build -trimpath ./cmd/lzug-admin
```

Die Python-Contract- und Persistenztests laufen mit `uv run --locked
--extra dev python -m unittest`. Das vollständige `task quality` bleibt die
breite Abnahme für diese sicherheits- und migrationsrelevante Änderung.
