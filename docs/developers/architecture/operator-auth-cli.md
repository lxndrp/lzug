# Betreiber-CLI für Authentifizierung und Ausschuss-Bootstrap

Die portable Go-CLI `lzug-admin` ist eine lokale Betriebsgrenze.
Sie öffnet keinen Netzwerk-Endpunkt und kennt weder SQLite noch SQLAlchemy.
Für jede Operation ruft sie das explizit benannte laufende Docker- oder Podman-Container- Objekt mit einzelnen Argumenten auf:

```text
lzug-admin --container <name> <command> [options]
  -> <engine> exec --interactive <name> python -m backend.admin --protocol 1
```

Der Containername wird gegen eine strikte Zeichenmenge geprüft.
Es gibt keine Shell-Stringverkettung, keine Compose-Namensauflösung und keinen vom Benutzer kontrollierten Befehl.
Ohne `--engine` wird zuerst Docker, danach Podman über `PATH` gesucht; ein gefundenes, aber nicht erreichbares Engine-Daemon bleibt als Betriebsfehler sichtbar.

## Versionierter Vertrag

Die Go-CLI sendet genau ein UTF-8-JSON-Objekt über stdin und leitet stdout und stderr des Python-Prozesses byteweise weiter.
Python antwortet mit genau einem JSON-Objekt und einer stabilen Prozesskennung:

```json
{
  "version": 1,
  "command": "invite",
  "arguments": {"email": "mitglied@example.invalid"}
}
```

Erfolgreiche Antworten haben `{"version":1,"ok":true,"result":{...}}`.
Fehler haben `{"version":1,"ok":false,"error":{"class":"...","message":"..."}}`.
Tokenwerte erscheinen ausschließlich in der erfolgreichen einmaligen Ausgabe einer Kontooperation oder in `result.invitations` eines neuen Ausschuss-Bootstraps beziehungsweise einer Neuausstellung.
Eine idempotente Wiederholung liefert denselben fachlichen Stand, aber kein Token erneut.
Fehlertexte, Diagnosen und Requestdaten spiegeln keine Token zurück.

| Exit-Code | Fehlerklasse | Bedeutung |
| ---: | --- | --- |
| 0 | — | erfolgreich |
| 2 | `invalid_request` | CLI-Argumente ungültig |
| 10 | `engine_unavailable` | Docker/Podman nicht auffindbar |
| 11 | `engine_invocation_failed` | Engine konnte nicht gestartet werden |
| 20 | `invalid_request` | JSON oder Protokoll ungültig |
| 21 | `database_not_ready` | Migration/Readiness nicht bereit |
| 22 | `bootstrap_not_empty` / `account_exists` / `*_conflict` | kontrollierter Konflikt |
| 23 | `account_not_found` / `committee_not_found` / `person_not_found` | Objekt nicht vorhanden oder nicht aktiv |
| 24 | `token_invalid` | Token ungültig, abgelaufen oder verbraucht |
| 25 | `persistence_error` | kontrollierter Persistenzfehler |
| 70 | `internal_error` | unerwarteter Fehler, fail-closed |

## Befehle und Sicherheitsgrenzen

- `bootstrap --email <email>` erstellt nur auf einer Datenbank ohne Konto das
erste aktive Betreiberkonto.
Es ist nicht mit `person` oder einer Ausschussmitgliedschaft verbunden und gibt eine 24 Stunden gültige Einladung einmalig aus.
- `invite --email <email>` erstellt ein nicht-operatives Konto und eine
24-Stunden-Einladung.
- `disable --account-id <id>` sperrt das Konto und widerruft seine aktiven
Sessions in derselben Transaktion.
- `recover (--account-id <id> | --email <email>)` löst für ein aktives Konto
einen 30 Minuten gültigen Recovery-Token aus.

Token werden mit kryptografisch zufälligem Material erzeugt und ausschließlich als SHA-256-Prüfwert in `auth_token` gespeichert.
Der interne Python-Service markiert die Werte beim Verbrauch atomar als verbraucht; Ablauf und Wiederholung werden identisch abgewiesen.
`consume-invitation` und `consume-recovery` lesen einen Token ausschließlich aus stdin und sind für Integrations- und spätere Auth-Flows vorgesehen.

Kennwort, Argon2id, TOTP und Recovery-Codes gehören weiterhin nicht zum Betreiber-CLI-Vertrag #269. #266 verwendet die dort ausgegebenen Einladungs- und Betreiber-Recovery-Token ausschließlich über die öffentlichen lokalen Auth-Flows und erweitert die CLI nicht.
Recovery-Codes sind davon strikt getrennte Mitgliedsgeheimnisse: Sie werden niemals von der CLI erzeugt oder ausgegeben.
Passkeys und OIDC bleiben die getrennten Folgearbeiten #267 und #268.

## Ausschuss-Bootstrap und technischer Lebenszyklus

Die Ausschussbefehle verwenden denselben stdin/stdout-Vertrag und dieselbe Containergrenze.
Die Go-CLI kennt weiterhin weder Datenbankpfad noch SQL und übergibt keine Einladungstoken in Prozessargumenten.

- `committee-bootstrap` verlangt eine eindeutige `--idempotency-key`, Bezeichnung, IHK und Ausbildungsberuf sowie genau einen expliziten bestehenden oder neuen Erstvorsitz.
  Eine abweichende Wiederholung derselben Kennung wird abgewiesen.
- `committee-complete` vervollständigt genau einen ungeklärten Altbestandsausschuss ohne aktiven Vorsitz anhand seiner stabilen ID.
- `committee-reinvite` stellt eine abgelaufene, nie aktivierte Einladung neu aus und invalidiert frühere offene Token atomar.
- `committee-deactivate` und `committee-reactivate` verlangen eine Begründung.
  Reaktivierung setzt genau einen aktiven Vorsitz und einen widerspruchsfreien Bootstrap-Zustand voraus.

Vorsitz und optionale Stellvertretung werden serverseitig fest auf `chair` beziehungsweise `deputy_chair` gesetzt.
Vertreterseite und Mitgliedsstatus müssen ausdrücklich angegeben werden; Clientfelder können weder Rolle, Aktivstatus noch fachlichen Akteur überschreiben.
Bestehende Personen werden nur über die normalisierte globale E-Mail-Adresse wiederverwendet und nicht verändert.
Ein neues Konto ist nicht-operativ, mit der Person verknüpft und erhält innerhalb derselben Transaktion eine 24-Stunden-Einladung.

Jede erfolgreiche Operation erzeugt in `committee_admin_operation` einen unveränderlichen, geheimnisfreien Nachweis mit Ausschuss-, Personen-, Mitgliedschafts- und Konto-IDs.
Die technische Quelle lautet `operator-cli`; eine fachliche Person wird nicht als Betreiberakteur erfunden.
Migration `021_add_committee_bootstrap.sql` klassifiziert Altbestand als `ready`, `needs_clarification` oder `conflict` und markiert die Herkunft als Migration, ohne eine ursprüngliche Betreiberhandlung zu behaupten.

Deaktivierte oder ungeklärte Ausschüsse werden bei jeder Autorisierungsprüfung aus aktiven fachlichen Scopes entfernt.
Bestehende Sitzungen und Berechtigungen derselben Person in anderen Ausschüssen bleiben erhalten.
Die produktive HTTP-API und Angular-Oberfläche bieten keine Ausschussanlage an; die öffentliche Demo besitzt dafür weder Rolle noch Capability oder Allowlist-Freigabe.

## Builds und lokale Prüfung

Die CLI wird unabhängig vom OCI-Image gebaut:

```sh
task test:operator
task quality:operator
task quality:operator-container
```

Der Qualitätstask führt die Vertragstests aus und baut die sechs portablen Kombinationen aus Linux, macOS und Windows für amd64 und arm64 in ein temporäres Verzeichnis.
Dadurch bleibt `dist/` unverändert.

Die Python-Contract- und Persistenztests laufen mit `uv run --locked --extra dev python -m unittest`.
Das vollständige `task quality` bleibt die breite Abnahme für diese sicherheits- und migrationsrelevante Änderung.
