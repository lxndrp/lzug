# `lzug-admin`-Befehlsreferenz

<!-- Generated from operator-cli/internal/admincli registry metadata. Do not edit directly. -->

Diese technische Referenz wird aus derselben statischen Registry wie Hilfe und Completion erzeugt.
Die handgeschriebenen Betriebsabläufe bleiben im Administrationshandbuch.

## Globale Optionen

| Option | Bedeutung | Werte/Standard |
| --- | --- | --- |
| `--engine ENGINE` | Container engine: auto, docker, or podman. | auto, docker, podman; Standard: auto |
| `--container NAME` | Exact running container name. | - |
| `--config FILE` | Read this explicit non-secret JSON configuration file. | - |
| `--no-config` | Do not read a configuration file. | - |
| `--json` | Write exactly one machine-readable result object to stdout. | - |
| `--verbose` | Write additional secret-free diagnostics to stderr. | - |
| `--force` | Skip an ordinary destructive-operation prompt. | - |
| `--help` | Globale oder kontextbezogene Hilfe ausgeben. | - |
| `--version` | CLI-Version ausgeben. | - |
| `--build-metadata` | Kanonische Build-Metadaten als JSON ausgeben. | - |

Konfigurierbar sind nur Engine und Containername.
Die Priorität lautet Flag vor Umgebungsvariable vor optionaler JSON-Datei vor Standardwert.

## Konfiguration und sichere Eingabe

Die Umgebungsvariablen `LZUG_ADMIN_ENGINE` und `LZUG_ADMIN_CONTAINER` sind die einzigen von der CLI ausgewerteten Konfigurationswerte.
Ohne `--config` sucht die CLI plattformgerecht unter dem durch `os.UserConfigDir` bestimmten Verzeichnis nach `lzug/admin.json`; eine fehlende Standarddatei ist zulässig.
Eine explizite fehlende oder ungültige Datei ist ein Konfigurationsfehler, und `--no-config` unterbindet jeden Dateizugriff.

```json
{"engine":"podman","container":"lzug"}
```

Andere Dateischlüssel sowie Umgebungsvariablen für Secrets, Bestätigungen oder Ausgabepräferenzen werden abgewiesen.
Einmaltoken und private Empfängerschlüssel besitzen keine CLI-Option und werden ausschließlich als einzelne Eingabe über `stdin` gelesen; am TTY bleibt die Eingabe ohne Echo.

## Ausgabe, Fehler und Bestätigung

Human-Ausgabe ist der Standard und bleibt bei einem vollständig spezifizierten erfolgreichen Vorgang grundsätzlich leer.
Erforderliche Einmalwerte und ausdrücklich abgefragte Diagnose erscheinen auf `stdout`; Fehler, Warnungen, Rückfragen und `--verbose`-Diagnose erscheinen auf `stderr`.
`--json` liefert bei Erfolg und Fehler genau ein Objekt mit `schema_version`, `protocol_version`, `ok`, `exit_code`, `command` und einem zulässigen `result` oder `error`.
Rohe Engine-Ausgabe, interne Backendtexte und nicht deklarierte Ergebnisfelder werden nicht weitergereicht.

| Exit Code | Bedeutung |
| --- | --- |
| `0` | Erfolg |
| `1` | Unerwarteter lokaler Fehler |
| `2` | Ungültiger Aufruf oder ungültige CLI-Eingabe |
| `10-19` | Lokale Umgebung oder Transport |
| `20-39` | Kontrollierter Backend-, Sicherheits-, Betriebs- oder Fachkonflikt |
| `40-49` | Versions- oder Protokollinkompatibilität |
| `130` | Abbruch durch `Ctrl+C` |

Gewöhnlich destruktive Commands fragen an einem TTY konkret nach und benötigen ohne TTY `--force`.
Als Danger Zone markierte semantische Flags bleiben davon unabhängig und werden durch `--force`, `--json` oder `--verbose` nie gesetzt.

## Geführter Modus

`lzug-admin cli` erzeugt einen zeilenorientierten Dialog vollständig aus derselben Registry und verwendet dieselben Parser, Handler, Validierungen, Renderer und Transportaufträge wie direkte Subcommands.
Ein- und Ausgabe müssen interaktive Terminals sein; `--json`, `--force`, Pipes und skriptgesteuerte Eingaben werden vor jedem Auftrag abgewiesen.
Das Sitzungsziel und seine Quelle bleiben sichtbar, werden vor dem ersten Backendauftrag geprüft und können nur für die laufende Sitzung geändert werden.
Geheimnisse werden ohne Echo für genau einen Versuch erfasst; Bestätigungen und Danger-Zone-Freigaben gelten ebenfalls nur für den dargestellten Auftrag.
Reguläres Beenden liefert Exit Code 0, `Ctrl+C` im Hauptmenü 130. Behandelte Commandfehler behalten im Dialog ihre eigene Fehlerklasse und ihren Exit Code, bestimmen aber nicht den Exit Code einer anschließend regulär beendeten Sitzung.

## Commands

### `lzug-admin account bootstrap`

Bootstrap an empty installation and issue its one-time invitation token.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--email EMAIL` | Account email address. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Prints the issued one-time token; JSON includes the validated backend result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug account bootstrap --email operator@example.invalid
```

### `lzug-admin account consume-invitation`

Read one invitation token from standard input and consume it through the local administration boundary.

Sichere Eingabe: One-time token read only from standard input.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Successful human output is silent; JSON includes the account result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
printf 'TOKEN' | lzug-admin --container lzug account consume-invitation
```

### `lzug-admin account consume-recovery`

Read one recovery token from standard input and consume it through the local administration boundary.

Sichere Eingabe: One-time token read only from standard input.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Successful human output is silent; JSON includes the account result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
printf 'TOKEN' | lzug-admin --container lzug account consume-recovery
```

### `lzug-admin account disable`

Disable one account and revoke its active sessions.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--account-id ID` | Positive account identifier. | Pflicht |

Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Successful human output is silent; JSON includes account and revocation details.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug account disable --account-id 7 --force
```

### `lzug-admin account invite`

Create or reuse an eligible account invitation and print its one-time token.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--email EMAIL` | Account email address. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Prints the issued one-time token; JSON includes the validated backend result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug account invite --email member@example.invalid
```

### `lzug-admin account recover`

Select exactly one account by identifier or email and issue a one-time recovery token.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--account-id ID` | Positive account identifier. | optional |
| `--email EMAIL` | Account email address. | optional |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Prints the issued one-time token; JSON includes the validated backend result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug account recover --account-id 7
lzug-admin --container lzug account recover --email member@example.invalid
```

### `lzug-admin artifact inspect`

Show format, protection method, and required fingerprint without an identity or business data.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--artifact PATH` | Regular protected artifact file. | Pflicht |

Transport: lokale Ausführung ohne Container-Auftrag.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Shows only the public preamble.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin artifact inspect --artifact backup.lzug
```

### `lzug-admin backup create`

Stream a backend-validated clear package directly into a local age-encrypted atomic target.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--output PATH` | New protected target artifact file. | Pflicht |

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Prints the activated local artifact path; JSON includes secret-free metadata.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug backup create --output backup.lzug
```

### `lzug-admin backup recipient replace`

Manage only the persistent public age recipient after local possession proof; private identities never reach the backend.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--identity-file PATH` | Protected local age identity file. | optional |
| `--identity-stdin` | Read the age identity from redirected standard input. | optional; Standard: false |
| `--identity-prompt` | Read the age identity from a hidden terminal prompt. | optional; Standard: false |

Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Shows the canonical public recipient and complete fingerprint.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug backup recipient replace --identity-file backup.agekey
```

### `lzug-admin backup recipient set`

Manage only the persistent public age recipient after local possession proof; private identities never reach the backend.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--identity-file PATH` | Protected local age identity file. | optional |
| `--identity-stdin` | Read the age identity from redirected standard input. | optional; Standard: false |
| `--identity-prompt` | Read the age identity from a hidden terminal prompt. | optional; Standard: false |

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Shows the canonical public recipient and complete fingerprint.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug backup recipient set --identity-file backup.agekey
```

### `lzug-admin backup recipient show`

Manage only the persistent public age recipient after local possession proof; private identities never reach the backend.

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Shows the canonical public recipient and complete fingerprint.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug backup recipient show
```

### `lzug-admin backup restore`

Decrypt locally, validate and stage in the backend, then activate only after every precheck succeeds.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--artifact PATH` | Regular protected artifact file. | Pflicht |
| `--replace` | Replace a non-empty installation after creating a safety artifact. | optional; Standard: false; separate Danger-Zone-Bestätigung |
| `--identity-file PATH` | Protected local age identity file. | optional |
| `--identity-stdin` | Read the age identity from redirected standard input. | optional; Standard: false |
| `--identity-prompt` | Read the age identity from a hidden terminal prompt. | optional; Standard: false |

Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Human success is silent; JSON includes restore phases and safety evidence.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug backup restore --artifact backup.lzug --identity-file backup.agekey --force
```

### `lzug-admin backup verify`

Decrypt locally and stream the clear package to the backend for complete validation.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--artifact PATH` | Regular protected artifact file. | Pflicht |
| `--identity-file PATH` | Protected local age identity file. | optional |
| `--identity-stdin` | Read the age identity from redirected standard input. | optional; Standard: false |
| `--identity-prompt` | Read the age identity from a hidden terminal prompt. | optional; Standard: false |

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Human success is silent; JSON contains the validated backend report.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug backup verify --artifact backup.lzug --identity-file backup.agekey
```

### `lzug-admin cli`

Start the line-oriented terminal dialog generated from this command registry. Interactive input and output terminals are required; --json and --force are invalid. Direct subcommands remain the interface for automation.

Transport: lokale Ausführung ohne Container-Auftrag.

Ausgabe: Runs the guided terminal session until the operator exits or interrupts it.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin cli
```

### `lzug-admin committee bootstrap`

Create one committee, select its initial chair and optional deputy, and issue any required invitations atomically.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--idempotency-key KEY` | Unique retry key with at least eight safe characters. | Pflicht |
| `--name NAME` | Committee name. | Pflicht |
| `--ihk NAME` | Responsible chamber of commerce. | Pflicht |
| `--occupation NAME` | Training occupation. | Pflicht |
| `--chair-existing-email EMAIL` | Chair existing person email. | optional |
| `--chair-first-name NAME` | Chair new person first name. | optional |
| `--chair-last-name NAME` | Chair new person last name. | optional |
| `--chair-email EMAIL` | Chair new person email. | optional |
| `--chair-mobile NUMBER` | Chair optional new person mobile number. | optional |
| `--chair-member-status STATUS` | Chair membership status. | optional |
| `--chair-representing-side SIDE` | Chair represented side. | optional |
| `--deputy-existing-email EMAIL` | Deputy chair existing person email. | optional |
| `--deputy-first-name NAME` | Deputy chair new person first name. | optional |
| `--deputy-last-name NAME` | Deputy chair new person last name. | optional |
| `--deputy-email EMAIL` | Deputy chair new person email. | optional |
| `--deputy-mobile NUMBER` | Deputy chair optional new person mobile number. | optional |
| `--deputy-member-status STATUS` | Deputy chair membership status. | optional |
| `--deputy-representing-side SIDE` | Deputy chair represented side. | optional |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints newly issued one-time invitation tokens; JSON includes the technical bootstrap result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug committee bootstrap --idempotency-key bootstrap-001 --name 'PA Nord' --ihk 'IHK Teststadt' --occupation 'Fachinformatiker/in' --chair-existing-email chair@example.invalid --chair-member-status ordinary --chair-representing-side employer
```

### `lzug-admin committee complete`

Complete one imported committee with its chair and optional deputy using an idempotent administration request.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--idempotency-key KEY` | Unique retry key with at least eight safe characters. | Pflicht |
| `--committee-id ID` | Positive committee identifier. | Pflicht |
| `--chair-existing-email EMAIL` | Chair existing person email. | optional |
| `--chair-first-name NAME` | Chair new person first name. | optional |
| `--chair-last-name NAME` | Chair new person last name. | optional |
| `--chair-email EMAIL` | Chair new person email. | optional |
| `--chair-mobile NUMBER` | Chair optional new person mobile number. | optional |
| `--chair-member-status STATUS` | Chair membership status. | optional |
| `--chair-representing-side SIDE` | Chair represented side. | optional |
| `--deputy-existing-email EMAIL` | Deputy chair existing person email. | optional |
| `--deputy-first-name NAME` | Deputy chair new person first name. | optional |
| `--deputy-last-name NAME` | Deputy chair new person last name. | optional |
| `--deputy-email EMAIL` | Deputy chair new person email. | optional |
| `--deputy-mobile NUMBER` | Deputy chair optional new person mobile number. | optional |
| `--deputy-member-status STATUS` | Deputy chair membership status. | optional |
| `--deputy-representing-side SIDE` | Deputy chair represented side. | optional |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints newly issued one-time invitation tokens; JSON includes the technical completion result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug committee complete --idempotency-key complete-001 --committee-id 7 --chair-existing-email chair@example.invalid --chair-member-status ordinary --chair-representing-side employer
```

### `lzug-admin committee deactivate`

Deactivate one committee with an idempotent, reasoned administration request.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--idempotency-key KEY` | Unique retry key with at least eight safe characters. | Pflicht |
| `--committee-id ID` | Positive committee identifier. | Pflicht |
| `--reason TEXT` | Required lifecycle reason. | Pflicht |

Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Successful human output is silent; JSON includes the technical lifecycle result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug committee deactivate --idempotency-key deactivate-001 --committee-id 7 --reason 'Operator decision' --force
```

### `lzug-admin committee reactivate`

Reactivate one committee with an idempotent, reasoned administration request.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--idempotency-key KEY` | Unique retry key with at least eight safe characters. | Pflicht |
| `--committee-id ID` | Positive committee identifier. | Pflicht |
| `--reason TEXT` | Required lifecycle reason. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Successful human output is silent; JSON includes the technical lifecycle result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug committee reactivate --idempotency-key reactivate-001 --committee-id 7 --reason 'Operator decision'
```

### `lzug-admin committee reinvite`

Reissue an invitation for one committee account through an idempotent administration request.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--idempotency-key KEY` | Unique retry key with at least eight safe characters. | Pflicht |
| `--committee-id ID` | Positive committee identifier. | Pflicht |
| `--email EMAIL` | Eligible committee account email address. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints the newly issued one-time invitation token; JSON includes the technical result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug committee reinvite --idempotency-key reinvite-001 --committee-id 7 --email member@example.invalid
```

### `lzug-admin completion bash`

Print an installable bash completion script derived only from static registry metadata.

Transport: lokale Ausführung ohne Container-Auftrag.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints the generated script; JSON returns the script as a string.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin completion bash > lzug-admin.bash
```

### `lzug-admin completion fish`

Print an installable fish completion script derived only from static registry metadata.

Transport: lokale Ausführung ohne Container-Auftrag.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints the generated script; JSON returns the script as a string.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin completion fish > lzug-admin.fish
```

### `lzug-admin completion powershell`

Print an installable powershell completion script derived only from static registry metadata.

Transport: lokale Ausführung ohne Container-Auftrag.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints the generated script; JSON returns the script as a string.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin completion powershell > lzug-admin.ps1
```

### `lzug-admin completion zsh`

Print an installable zsh completion script derived only from static registry metadata.

Transport: lokale Ausführung ohne Container-Auftrag.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints the generated script; JSON returns the script as a string.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin completion zsh > lzug-admin.zsh
```

### `lzug-admin config inspect`

Show the effective engine and container together with their flag, environment, file, or default source. No configuration is changed.

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints effective non-secret values and their source; JSON exposes the same fields.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin config inspect
lzug-admin --no-config --engine podman --container lzug config inspect --json
```

### `lzug-admin export create`

Stream a backend-validated clear package directly into a local age-encrypted atomic target.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--output PATH` | New protected target artifact file. | Pflicht |
| `--recipient AGE_RECIPIENT` | Explicit public X25519 age recipient. | Pflicht |

Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Prints the activated local artifact path; JSON includes secret-free metadata.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug export create --recipient age1... --output export.lzug --force
```

### `lzug-admin export verify`

Decrypt locally and stream the clear package to the backend for complete validation.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--artifact PATH` | Regular protected artifact file. | Pflicht |
| `--identity-file PATH` | Protected local age identity file. | optional |
| `--identity-stdin` | Read the age identity from redirected standard input. | optional; Standard: false |
| `--identity-prompt` | Read the age identity from a hidden terminal prompt. | optional; Standard: false |

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Human success is silent; JSON contains the validated backend report.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug export verify --artifact export.lzug --identity-file backup.agekey
```

### `lzug-admin notification process`

Process due notification deliveries and confirmed-plan consequences without returning message content.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `10m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Successful human output is silent; JSON includes technical counters only.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug notification process
```

### `lzug-admin notification test`

Run a technical synthetic delivery for one committee member without returning message content.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--member-id ID` | Positive committee member identifier. | Pflicht |
| `--channel CHANNEL` | Notification channel. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Successful human output is silent; JSON includes synthetic technical delivery details.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug notification test --member-id 7 --channel web_push
```

### `lzug-admin plan-consequence retry`

Retry eligible technical follow-up work for one confirmed plan revision without exposing business content.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--revision-id ID` | Positive confirmed plan revision identifier. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `10m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Geführter Modus: zeigt vor der Ausführung Ziel, Wirkung und alle nicht geheimen Parameter.

Ausgabe: Successful human output is silent; JSON includes technical counters only.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug plan-consequence retry --revision-id 17
```

### `lzug-admin plan-consequence status`

Inspect technical follow-up states for one confirmed plan revision without exposing business content.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--revision-id ID` | Positive confirmed plan revision identifier. | Pflicht |

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints a technical status summary; JSON includes the validated technical result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug plan-consequence status --revision-id 17
```

### `lzug-admin recipient-key generate`

Create a protected private identity and a shareable public recipient atomically without overwriting files.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--identity-file PATH` | New private identity file. | Pflicht |
| `--recipient-file PATH` | New public recipient file. | Pflicht |

Transport: lokale Ausführung ohne Container-Auftrag.

Ausgabe: Human output reminds about independent key backup; JSON excludes the private identity.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin recipient-key generate --identity-file backup.agekey --recipient-file backup.agepub
```

### `lzug-admin recipient-key inspect`

Show only the canonical public recipient, method, and complete fingerprint.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--key-file PATH` | Private identity or public recipient file. | Pflicht |

Transport: lokale Ausführung ohne Container-Auftrag.

Ausgabe: Shows no private identity value.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin recipient-key inspect --key-file backup.agekey
```

### `lzug-admin system config`

Validate the runtime's secret-free configuration contract. The backend receives no operator secrets or business data.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints a secret-free status and check summary; JSON includes the validated diagnostic result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug system config
```

### `lzug-admin system doctor`

Run runtime, schema, persistence, storage, and readiness diagnostics. The backend receives no operator secrets or business data.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints a secret-free status and check summary; JSON includes the validated diagnostic result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug system doctor
```

### `lzug-admin system status`

Inspect runtime identity and application readiness. The backend receives no operator secrets or business data.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Prints a secret-free status and check summary; JSON includes the validated diagnostic result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug system status
```

### `lzug-admin upgrade apply`

Create and locally decrypt a protected safety backup before applying supported migrations in a maintenance container.

| Option | Bedeutung | Pflicht/Standard |
| --- | --- | --- |
| `--backup-output PATH` | New local protected pre-upgrade backup. | Pflicht |
| `--identity-file PATH` | Protected local age identity file. | optional |
| `--identity-stdin` | Read the age identity from redirected standard input. | optional; Standard: false |
| `--identity-prompt` | Read the age identity from a hidden terminal prompt. | optional; Standard: false |
| `--confirm-irreversible` | Confirm pending irreversible migrations when the backend requires it. | optional; Standard: false; separate Danger-Zone-Bestätigung |

Bestätigung: interaktive TTY-Rückfrage oder `--force`; separate Danger-Zone-Flags werden dadurch nicht gesetzt.

Transport: lokale Orchestrierung über den gemeinsamen Docker-/Podman-Containertransport; geheimes Schlüsselmaterial verbleibt in der CLI.

Ausgabe: Successful human output is silent; JSON includes the validated lifecycle result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `local`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug-maintenance upgrade apply --backup-output pre-upgrade.lzug --identity-file backup.agekey --force
```

### `lzug-admin upgrade rollback`

Verify CLI and container release identity and evaluate rollback eligibility without mutating the installation.

Transport: versionierter Auftrag über den gemeinsamen Docker-/Podman-Containertransport.

Zeitlimit: `2m0s`; nach einem Timeout muss der Auftragsstatus vor einer Wiederholung geprüft werden.

Wiederholung: im geführten Modus nach kontrollierten Fehlern als sicher eingestuft; Geheimnisse und Bestätigungen werden neu erfasst.

Ausgabe: Successful human output is silent; JSON includes the validated rollback result.
`--verbose` ergänzt geheimnisfreien Fortschritt und die Ergebniszusammenfassung auf `stderr`; `--json` verwendet den deklarierten `projected`-Ergebnisvertrag auf `stdout`.

```console
lzug-admin --container lzug-maintenance upgrade rollback
```

## Migration der alten Syntax

Die alten flachen Formen sind keine Aliase und werden als ungültiger Aufruf abgewiesen.

| Alte Form bis v0.6.x | Neue Form ab v0.7.0 |
| --- | --- |
| `lzug-admin artifact-verify (backup artifact)` | `lzug-admin backup verify` |
| `lzug-admin artifact-verify (full-export artifact)` | `lzug-admin export verify` |
| `lzug-admin backup-create` | `lzug-admin backup create` |
| `lzug-admin backup-restore` | `lzug-admin backup restore` |
| `lzug-admin bootstrap` | `lzug-admin account bootstrap` |
| `lzug-admin committee-bootstrap` | `lzug-admin committee bootstrap` |
| `lzug-admin committee-complete` | `lzug-admin committee complete` |
| `lzug-admin committee-deactivate` | `lzug-admin committee deactivate` |
| `lzug-admin committee-reactivate` | `lzug-admin committee reactivate` |
| `lzug-admin committee-reinvite` | `lzug-admin committee reinvite` |
| `lzug-admin config` | `lzug-admin system config` |
| `lzug-admin consume-invitation` | `lzug-admin account consume-invitation` |
| `lzug-admin consume-recovery` | `lzug-admin account consume-recovery` |
| `lzug-admin disable` | `lzug-admin account disable` |
| `lzug-admin doctor` | `lzug-admin system doctor` |
| `lzug-admin full-export` | `lzug-admin export create` |
| `lzug-admin invite` | `lzug-admin account invite` |
| `lzug-admin plan-consequences-status` | `lzug-admin plan-consequence status` |
| `lzug-admin process-notifications` | `lzug-admin notification process` |
| `lzug-admin recover` | `lzug-admin account recover` |
| `lzug-admin retry-plan-consequences` | `lzug-admin plan-consequence retry` |
| `lzug-admin rollback` | `lzug-admin upgrade rollback` |
| `lzug-admin status` | `lzug-admin system status` |
| `lzug-admin test-notification` | `lzug-admin notification test` |
| `lzug-admin upgrade` | `lzug-admin upgrade apply` |
