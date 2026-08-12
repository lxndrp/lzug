# Sicherheitsrichtlinie

lzug ist ein öffentlich entwickeltes Projekt vor der ersten stabilen
Produktionsfreigabe. Self-Hosting und Release-Kandidaten erhalten automatisierte
Security-Prüfungen; daraus entsteht noch keine Zusicherung für ungeprüfte
Installationen oder ältere Stände.

## Unterstützte Stände

Aktuell wird ausschließlich der freigegebene Stand von `master` unterstützt.
Es gibt noch keine stabilen Releases und keine Sicherheitsupdates für ältere
Commits. Nach der ersten versionierten Veröffentlichung wird diese Tabelle um
die konkret unterstützten Release-Linien ergänzt.

| Stand | Unterstützt |
| --- | --- |
| aktueller `master` | ja |
| ältere Commits und Vorabstände | nein |

## Sicherheitslücken vertraulich melden

Bitte veröffentliche vermutete Sicherheitslücken nicht als Issue, Pull Request
oder Diskussion. Verwende stattdessen das aktivierte
[Private Vulnerability Reporting](https://github.com/lxndrp/lzug/security/advisories/new).

Eine Meldung sollte, soweit ohne zusätzliche Gefährdung möglich, enthalten:

- betroffene Version, Commit oder Komponente;
- Auswirkung und realistisches Angriffsszenario;
- reproduzierbare Schritte oder einen minimalen Nachweis;
- bekannte Abhilfen oder Randbedingungen.

Sende keine realen Zugangsdaten, Tokens, TOTP-Secrets oder personenbezogenen
Daten. Verwende ausschließlich synthetische Beispiele.

Der Maintainer bestätigt Meldungen und stimmt Prüfung, Behebung, Advisory und
Veröffentlichung nach bestem Vermögen vertraulich ab. Eine feste Reaktions-
oder Behebungsfrist kann vor dem ersten stabilen Release noch nicht zugesichert
werden.

## Technische Baseline

- GitHub Secret Scanning und Push Protection sind aktiviert; Private
  Vulnerability Reporting ist der verbindliche Meldeweg.
- CodeQL analysiert Python, JavaScript/TypeScript und Go auf jedem Pull Request.
  GitHubs native Ruleset-Regel `Require code scanning results` blockiert
  Security-Befunde ab `high_or_higher`; normale Fehlerwarnungen sind mit
  `alerts_threshold=none` nicht Teil der Merge-Sperre.
- Trivy prüft den Quellbaum auf Secrets/Misconfiguration sowie das tatsächlich
  gebaute Image auf behebbare High/Critical-Abhängigkeiten, Secrets und
  Misconfiguration. Ein CycloneDX-SBOM wird als CI-Artefakt erzeugt.
- Der Security-Workflow besitzt minimal erforderliche Tokenrechte; sämtliche
  dort verwendeten Actions sind auf vollständige Commit-SHAs fixiert.
- Das OCI-Image läuft als UID/GID `10001:10001`, enthält weder Demo-Daten noch
  Build-Toolchain oder eingebettete Secrets und unterstützt read-only Root-FS,
  Capability-Drop und `no-new-privileges`.
- Die HTTP-Runtime erzwingt Session, CSRF, Actor- und Ausschusskontext
  serverseitig. Unberechtigte Schreibzugriffe liefern 403; lesende Zugriffe auf
  fremde Ausschussressourcen verbergen deren Existenz mit 404. Health ist die
  einzige öffentliche GET-API und enthält nur den Readiness-Status.
- Security-Header, same-origin CORS, sichere Cookies, Request-/Upload-Limits,
  Auth-Rate-Limits und secret-freie Access-Logs sind produktive Defaults.

Die vollständige technische Begründung, Grenzwerte und Gate-Matrix stehen in der
[Veröffentlichungs- und Runtime-Sicherheitsbaseline](docs/developers/architecture/security-baseline.md).

## Sicherheitsgrenzen

- Kontenpflege erfolgt ausschließlich über die lokale Betreiber-CLI; es gibt
  keinen Netzwerk-Admin-Endpunkt und keinen direkten SQLite-Zugriff der Go-CLI.
- Betreiberidentität verleiht keine fachliche Ausschussrolle.
- Passkeys und OIDC sind nicht Bestandteil dieser Baseline und bleiben die
  getrennten Ausbaustufen #267 und #268.
- Demo- und Testdaten müssen synthetisch bleiben. lzug ist keine offizielle
  Anwendung oder Veröffentlichung einer IHK.
