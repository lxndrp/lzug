# Continuous Integration

## Zwei getrennte Qualitätsabläufe

Pull Requests und der integrierte Stand besitzen bewusst unterschiedliche
Workflows:

- `.github/workflows/pull-request.yml` wählt mit der auf einen Commit gepinnten
  Action `dorny/paths-filter` nur die betroffenen Qualitätsdomänen aus.
- `.github/workflows/quality.yml` prüft jeden Push auf `master`, den
  Wochenzeitplan und jeden manuellen Start vollständig. Dieser Workflow enthält
  weder Pfadklassifikation noch Kompatibilitäts-Gates für Required Checks.

Der erfolgreiche vollständige Workflow-Lauf `Quality` auf einer konkreten
`master`-SHA ist damit der Qualitätsnachweis, den der in
[ADR-0020](decisions/0020-minimaler-releaseablauf-mit-github-bordmitteln.md)
beschlossene Releaseablauf verwendet. Interne Jobnamen sind kein
Releasevertrag.

## Stabiler Pull-Request-Vertrag

Das Ruleset verlangt genau diese fünf immer vorhandenen Gate-Namen:

| Required Check | Ausgeführte Qualitätsaussage |
| --- | --- |
| `Pull Request / Documentation` | strikter MkDocs-Build und TypeDoc |
| `Pull Request / Backend` | Ruff, Black, Python-Audit, Tests und Coverage; bei produktiven Webänderungen zusätzlich E2E und Accessibility |
| `Pull Request / Frontend` | ESLint, Prettier, Angular-Build, Tests, Coverage und npm-Produktionsaudit; bei produktiven Webänderungen zusätzlich E2E und Accessibility |
| `Pull Request / CLI` | Go-Vertrag sowie mit GoReleaser reproduzierbar gebaute Archive für Linux, macOS und Windows auf amd64 und arm64 |
| `Pull Request / Container` | einmal gebautes OCI-Image, SBOMs, Image-Scan sowie Container-, Compose- und CLI-zu-Container-Verträge; bei Infrastrukturänderungen zusätzlich OpenTofu-Format, -Validierung und gemockter Plan |

Das manuelle Azure-Demo-Deployment ist vom CI- und Publish-Lebenszyklus
getrennt. Es verwendet ausschließlich OIDC, ein geschütztes GitHub Environment
und ein zuvor geprüftes App-/Seed-Digest-Paar. Der repositoryseitige Vertrag
wird mit `task quality:demo-deployment` ohne Cloudzugriff geprüft; Details
stehen unter [Azure-Demo deployen](demo-deployment.md).

Jedes Gate läuft mit `if: always()`. Ist seine Domäne nicht ausgewählt, prüft
es ausdrücklich den Status `skipped` des Detailjobs und wird selbst
erfolgreich. Ausgewählte Details müssen dagegen `success` melden. Ein Fehler
der Pfadauswahl, des breiten Source-Scans oder einer CodeQL-Analyse lässt alle
Gates fail-closed fehlschlagen.

CodeQL analysiert Python, JavaScript/TypeScript und Go auf jedem Pull Request.
GitHubs native Ruleset-Regel `Require code scanning results` bleibt mit
`security_alerts_threshold=high_or_higher` aktiv. Der Trivy-Scan auf Secrets
und Fehlkonfigurationen bleibt ebenfalls bewusst breit. Beide Nachweise sind
keine zusätzliche projektspezifische Qualitätsdomäne.

Beide Workflows setzen für CodeQL weiterhin die vor #344 verwendete Kategorie
`.github/workflows/ci.yml:codeql/language:<Sprache>`. Dieser Wert ist eine
stabile Analyse-ID und kein Verweis auf einen vorhandenen Workflow. Er bewahrt
beim Workflow-Split die Vergleichbarkeit mit den auf `master` registrierten
Analysen und darf bei einer späteren Dateiumbenennung nicht implizit wechseln.

## Konservative Pfadauswahl

Die Pfadauswahl bildet fachlich verständliche Repositorygrenzen auf fünf
stabile Gates ab. Infrastruktur ist eine eigene Detaildomäne und läuft in das
bestehende Container-Gate ein:

| Änderung | Auswahl |
| --- | --- |
| `docs/**`, MkDocs, Changelog oder dokumentierende README-Dateien | Dokumentation |
| `backend/**`, Datenbankschema, Migrationen, Fixtures oder Prototypen | Backend |
| Frontend-Code und Frontend-Konfiguration außer reinen Markdown-Dateien | Frontend |
| `cmd/lzug-admin/**` | CLI |
| Dockerfile, Docker-Kontext, Compose-Referenz oder Umgebungsbeispiel | Container |
| `infra/**` | Infrastruktur; der Nachweis läuft in das stabile Container-Gate ein |
| produktives Backend, Datenmodell, Fixtures, Frontend-Produktcode oder Playwright | zusätzlich getrennte E2E- und Accessibility-Jobs |
| Workflows, Toolchain, Taskfile, Lockfiles, Dependency-Manifeste oder `scripts/**` | alle Detaildomänen und beide Browserjobs |
| leerer oder keiner bekannten Grenze zugeordneter Pfad | alle Detaildomänen und beide Browserjobs |

Reine Backend-Tests und `*.spec.ts`-Frontend-Tests wählen keine Browserjobs.
Mehrere Änderungen vereinigen ihre Domänen. Prozessdateien wie `AGENTS.md`,
`CONTRIBUTING.md` oder Issue-Prozessvorlagen sind bekannte Grenzen ohne
Anwendungsdomäne; die fünf Gates bleiben sichtbar erfolgreich, während
CodeQL und Source-Scan weiterhin laufen.

Die Pfadfilter-Action liest bei Pull Requests die geänderten Dateien über die
GitHub-API. Ein zweiter Filter verwendet die `every`-Semantik, um jeden nicht
bekannten Pfad zu erkennen. Dadurch kann eine neue Repositorygrenze nicht
unbemerkt sämtliche fachlichen Prüfungen überspringen.

## Vollständiger `master`-Vertrag

`quality.yml` führt unabhängig vom Änderungsumfang parallel aus:

- Backend-, Frontend-, Dokumentations- und CLI-Qualität,
- OpenTofu-Format, -Validierung und gemockter Infrastrukturplan ohne Cloudzugriff,
- npm- und Python-Abhängigkeitsaudits,
- OCI-Build, Dependency- und Image-SBOM, Trivy-Image-Scan,
- Container-, Compose- und CLI-zu-Container-Verträge,
- Browser-E2E und Accessibility als getrennte Jobs,
- Source-Scan und CodeQL für alle drei vorhandenen Sprachen.

Die Domänenjobs rufen dieselben `task`-Teilaufgaben auf wie die lokale
Qualitätssicherung. Der vollständige Lauf besitzt keine Pfadausgaben, keine
ausgewählten oder übersprungenen Details und keinen künstlichen
Required-Check-Gesamtstatus. Sein Workflow-Ergebnis ist der vollständige
Nachweis für die geprüfte SHA.

`task quality:operator` validiert die gepinnte GoReleaser-Konfiguration und
baut den vollständigen Sechs-Plattform-Snapshot zweimal. Die Prüfung vergleicht
Binärdateien und Archive bytegenau und kontrolliert Namen, Inhalte,
Build-Metadaten sowie die Abwesenheit einer GoReleaser-Checksummendatei. Der
Releaseablauf übernimmt später nur diese sechs Archive; Attestations und die
eine aggregierte CycloneDX-SBOM bleiben davon getrennt.

## Kontrollierte Ruleset-Migration

Die Migration von den früheren sieben `Quality / …`-Checks erfolgt ohne Phase
fehlenden Schutzes:

1. Ein Pull Request führt zunächst die fünf neuen Gates sowie CodeQL und den
   Source-Scan erfolgreich aus, während die bisherigen Required Checks noch
   aktiv sind.
2. Das aktive Ruleset wird in einer einzelnen kontrollierten Änderung von den
   sieben alten auf die fünf neuen Gate-Namen umgestellt.
3. `strict_required_status_checks_policy=true`, die native CodeQL-Regel, das
   aktive Enforcement und die leere Bypass-Liste bleiben unverändert.
4. Erst der unter dieser Zielkonfiguration erneut geprüfte Pull Request darf
   durch einen Maintainer gemergt werden.

Der Release-Workflow liest ausschließlich den erfolgreichen vollständigen
`Quality`-Workflow-Lauf derselben `master`-SHA. Er fragt keine internen
Jobnamen ab und wiederholt keine der hier beschriebenen Qualitätsprüfungen.

## Messung der Vereinfachung und Laufzeit

Vor #344 bestanden die eigene PR-/Master-Orchestrierung aus 904 Workflowzeilen,
274 Zeilen Python-Klassifizierer und 453 Zeilen zugehörigen Workflow-, OCI- und
Security-Vertragstests, zusammen 1.631 Zeilen. Die Umstellung entfernt den
Klassifizierer vollständig. Bei Abschluss dieser Umstellung umfassten die
beiden getrennten Workflows und die auf Verhalten reduzierten Vertragstests
zusammen 952 Zeilen: 679 Zeilen beziehungsweise 41,6 % weniger eigener
Orchestrierungs- und Testcode. Spätere Domänen wie die Infrastrukturprüfung
sind nicht Teil dieser historischen Messung.

Für die Laufzeit bleiben verstrichene Workflow-Zeit und summierte
Runner-Jobsekunden getrennt. Die belegte Ausgangsbasis für reine Dokumentation
ist Lauf
[`31544471092`](https://github.com/lxndrp/lzug/actions/runs/31544471092)
mit 85 Sekunden und zwölf Jobs. Für eine reine CLI-Änderung existiert im
aktuellen Workflowbestand kein isolierter historischer PR-Lauf; deshalb wird
kein synthetischer Ist-Wert als Messung ausgegeben. Stattdessen vergleicht der
umsetzende Pull Request die realen Laufzeiten der neuen Dokumentations- und
CLI-Details sowie der gemeinsamen CodeQL-/Source-Scan-Komponenten mit den
entsprechenden Jobs des letzten vollständigen Ausgangslaufs. Da diese
Komponenten parallel laufen, ist für die PR-Dauer jeweils der längste
notwendige Pfad maßgeblich, nicht ihre Summe.

## Lokale Qualitätssicherung

Die lokale Auswahl bleibt in `Taskfile.yml` kanonisch:

- `task quality:backend`, `task quality:frontend`, `task quality:operator`,
  `task quality:infra`, `task quality:oci`, `task quality:compose-config`,
  `task quality:overall` und `task docs` für begrenzte Änderungen,
- `task quality:release` für den Release-, Metadaten-, GoReleaser- und
  aggregierten SBOM-Vertrag ohne Veröffentlichung,
- `task quality` für CI-, Toolchain-, Dependency-, Security- oder andere
  querschnittliche Änderungen.

E2E und Accessibility bleiben getrennte Tasks. Vor gezielten Browserprüfungen
ist `task doctor` auszuführen. Lokale Docker- und Podman-Prüfungen nutzen
denselben gebauten Image-Vertrag und dieselbe Container-Orchestrierung;
`quality:compose-config` verwendet mit beiden Engines deren
Standard-Compose-Validierung vor der getrennten lzug-Policy. CodeQL und der
gehostete Source-Scan bleiben GitHub-gebundene Ergänzungen. Die allgemeine
risikobasierte Auswahl ist in
[ADR-0009](decisions/0009-toolchain-und-entwicklungs-tasks.md) beschrieben.
