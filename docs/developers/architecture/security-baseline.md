# Veröffentlichungs- und Runtime-Sicherheit

Diese Baseline ist das produktive Security-Gate für die erste Self-Hosting-
Auslieferung. Sie ergänzt die Repository-Baseline und die Authentifizierung,
zieht aber weder Passkeys (#267) noch OIDC (#268) vor.

## Öffentliche HTTP-Grenze

Ohne Session sind ausschließlich folgende Routen erreichbar:

| Route | Begründung und Schutz |
| --- | --- |
| `/` und statische SPA-Dateien | liefern die Anmeldeoberfläche; CSP, Frame-, Referrer- und weitere Browserheader gelten auch hier |
| `GET /api/health` | liefert nur `status` und den Self-Link, keine Fachdaten, Migrationsnamen oder Betriebsdetails |
| `POST /api/auth/login` | notwendiger Anmeldeeinstieg; generische Fehler, Größenlimit und zweistufiges Rate Limit |
| `POST /api/auth/invitation/*` | einmalige, kurzlebige Tokens ausschließlich im JSON-Body; Rate Limit und generische Fehler |
| `POST /api/auth/recovery/*` | einmalige, kurzlebige Tokens ausschließlich im JSON-Body; Rate Limit und generische Fehler |

`/api`, `/api/openapi.json`, `/api/docs` und alle Fachrouten benötigen eine
gültige Session. Fehlende oder ungültige Authentifizierung liefert 401. Eine
gültige Session ohne aktiven Fach-Actor, ein schreibender fremder
Ausschusskontext, ein unzulässiges Recht oder eine fehlerhafte CSRF-Prüfung
liefert 403. Lesende Zugriffe auf fremde Ausschussressourcen liefern 404, damit
deren Existenz nicht offengelegt wird. Vom Client übermittelte
`created_by_member_id`- und `updated_by_member_id`-Werte werden entfernt und
aus der Session neu aufgelöst.

Die produktive Runtime sendet `Content-Security-Policy`, `X-Frame-Options`,
`X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`,
`Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` und bei
HTTPS-Betrieb HSTS. API-Antworten sind nicht cachebar. Die frühere
Swagger-Ausgabe mit externem JavaScript wurde durch eine lokale, skriptfreie
Dokumentationsseite ersetzt.

CORS ist standardmäßig deaktiviert. `LZUG_CORS_ALLOWED_ORIGINS` akzeptiert nur
exakte, kommaseparierte HTTP(S)-Origins; Wildcards, Pfade und Origins mit
Zugangsdaten verhindern den Start. Nur ein exakt erlaubter Origin erhält
Credential- und Preflight-Header. Browseranfragen aus anderen Origins werden
vor Authentifizierung und Body-Verarbeitung mit 403 abgewiesen.

## Laufzeitparameter

| Variable | Standard | Sicherheitsgrenze |
| --- | --- | --- |
| `LZUG_HTTPS_ONLY` | `true` | aktiviert `__Host-`-Secure-Cookie und HSTS; `false` verwendet nur für einen lokalen Test das unpräfixierte `lzug_session` |
| `LZUG_CORS_ALLOWED_ORIGINS` | leer | same-origin; nur exakte Origins, niemals `*` |
| `LZUG_SESSION_TTL_SECONDS` | `28800` | 5 Minuten bis höchstens 24 Stunden; Cookie- und serverseitige Laufzeit stimmen überein |
| `LZUG_MAX_REQUEST_BYTES` | `1048576` | maximales JSON-Request-Body; größere Bodies liefern 413 |
| `LZUG_AUTH_RATE_LIMIT` | `20` | maximale öffentliche Auth-Requests je IP und Route im Zeitfenster |
| `LZUG_AUTH_RATE_WINDOW_SECONDS` | `60` | Zeitfenster des allgemeinen Auth-Limits |
| `LZUG_MAX_UPLOAD_BYTES` | `10485760` | maximale Dokumentgröße; gilt auch für Streams |
| `LZUG_ALLOWED_UPLOAD_MEDIA_TYPES` | `application/pdf,image/jpeg,image/png,text/plain` | exakte Medientyp-Allowlist; insbesondere kein SVG/HTML |

Der Login besitzt zusätzlich das in der
[Authentifizierungsarchitektur](authentication.md) beschriebene
Fehlversuchs-Limit. JSON-Bodies benötigen `Content-Type: application/json`;
Chunked Transfer-Encoding wird vom einfachen HTTP-Adapter nicht akzeptiert.

Der Access-Log enthält ausschließlich Methode, Pfad ohne Query, Status und
Antwortgröße. Client-IP, Query-Parameter, Header, Cookies, Tokens und
Request-Bodies werden nicht protokolliert. Fach- und Persistenzfehler werden
auf stabile öffentliche Meldungen abgebildet.

## Containergrenze

Der Docker-Build-Kontext verwendet eine deny-by-default `.dockerignore` und
überträgt nur die explizit benötigten Lockfiles, Quellen, Migrationen und
Frontend-Dateien. Das Image enthält insbesondere keine `.env`-Dateien,
Git-Historie, Tests, Demo-Daten oder lokale Schlüssel. Es läuft als
`10001:10001`, enthält die lokale Authentifizierung und bleibt mit
schreibgeschütztem Root-Dateisystem, Capability-Drop und
`no-new-privileges` betreibbar.

`scripts/container-smoke.sh` bindet synthetische Seed-Daten ausschließlich für
den Test ein. Der Test prüft Non-Root, minimales öffentliches Health,
Security-Header, 401, Operator-/Actor-403, verdeckte fremde Reads mit 404,
schreibende Ausschussisolation mit 403, serverseitiges Überschreiben eines
manipulierten Actors, sichere Cookies und secret-freie Logs. Das
veröffentlichte Image enthält diese Seed-Datei nicht.

## Blockierende Security-Gates

Der konsolidierte Workflow `.github/workflows/ci.yml` besitzt global nur
`contents: read`. `security-events: write` ist ausschließlich auf die beiden
CodeQL-Matrixjobs begrenzt. Alle Actions sämtlicher Workflows sind auf
vollständige Commit-SHAs fixiert; ein repositoryweiter Vertragstest verhindert
bewegliche Tag-Referenzen auch in Release-, Dependabot- und Wiki-Abläufen.

| Gate | Blockierender Befund | Nachweis |
| --- | --- | --- |
| CodeQL für Python und JavaScript/TypeScript | `security-severity >= 7.0` | SARIF wird hochgeladen und zusätzlich durch `scripts/enforce_sarif_security.py` ausgewertet |
| Trivy-Quellscan | Secrets oder High/Critical-Misconfiguration | aktueller Quellbaum ohne Git-, venv- oder `node_modules`-Inhalte |
| Reproduzierbarer Image-Build und Runtime-Smoke | Buildfehler, abweichender Runtime-User oder verletzte HTTP-/Isolationsgrenze | einmaliger Build aus Lockfiles, Image-User `10001:10001` und `scripts/container-smoke.sh` gegen das per Prüfsumme übergebene Build-Artefakt |
| Trivy-Imagescan | behebbare High/Critical OS-/Bibliothekslücke, Secret oder Misconfiguration | dasselbe per Prüfsumme übergebene Image wie im Runtime-Smoke |
| SBOM | fehlendes oder leeres CycloneDX-Dokument | 30 Tage aufbewahrtes CI-Artefakt |

Trivy ist als vollständiger SHA der laut
[offiziellem Advisory](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)
abgesicherten Action 0.35.0 fixiert und verwendet die unveränderliche Version
0.69.3. Der SARIF-Filter besitzt Positiv- und Negativtests; die Workflowtests
prüfen SHA-Pins und blockierende Scannerkonfiguration. Scannerbefunde werden
nicht durch gelockerte Schwellen oder pauschale Ignore-Dateien verborgen.

Der Qualitätsworkflow läuft auf jedem Push nach `main` oder `master`, im
wöchentlichen Zeitplan und bei manueller Ausführung vollständig. In Pull
Requests wählt die zentrale konservative Klassifikation die betroffenen
Domänen und Overall-Verträge; leere oder unbekannte Pfadmengen führen immer zum
Vollauf. Pull Requests lesen nur den gemeinsamen BuildKit-Cache.
Ausschließlich ein Push auf den geschützten Hauptbranch darf ihn aktualisieren.
Image-Build, Image-Scan und die Container-, Compose- sowie CLI-zu-Container-
Verträge bleiben getrennte Statuschecks. Das Image-Archiv wird einmal gebaut,
mit SHA-256 abgesichert und in jedem ausgewählten Folgejob vor Verwendung
geprüft. `Quality / OCI` verlangt Build und Scan, `Quality / Overall` die
ausgewählten Laufzeitverträge. Der vorübergehende
`OCI pull request gate`-Kompatibilitätsstatus hängt vom neuen OCI-Gate ab und
kann es nicht umgehen.

GitHub Secret Scanning und Push Protection sind im öffentlichen Repository
aktiv. Non-Provider-Patterns und Validity Checks werden vom aktuellen
Repository-/Tarifkontext nicht angeboten und blieben bei der Aktivierungsprüfung
deaktiviert. Private Vulnerability Reporting ist als vertraulicher Meldeweg
aktiviert.
