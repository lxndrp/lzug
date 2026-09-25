# Entwicklung

[`CONTRIBUTING.md`](https://github.com/lxndrp/lzug/blob/master/CONTRIBUTING.md)
enthält die verbindlichen Beitragsregeln.
Diese Seite bündelt die revisionsgebundenen technischen Einstiege,
Einrichtung, Arbeitsprozess und passende lokale Prüfungen.

## Toolchain und Einrichtung

`mise` stellt die projektweit gepinnten Werkzeuge bereit.
Die ausgewählten Versionen stehen in `.mise.toml` und den jeweiligen
Ökosystemdateien;
ihre Rollen als Auswahl, Lockfile-Auflösung oder Nachweis folgen
[ADR-0034](decisions/0034-versionsbindung-und-unveraenderliche-referenzen.md).
`uv.lock`, `frontend/package-lock.json` und `operator-cli/go.sum` binden die
Abhängigkeiten.

```sh
mise install
mise exec -- task setup
mise exec -- task doctor
```

`task setup` erzeugt `.venv`, synchronisiert die gelockten Python-Pakete,
installiert das Frontend mit `npm ci`.
PowerShell 7.5.3 wird über `.mise.toml` bereitgestellt und verbindet die
wenigen plattformabhängigen Werkzeuggrenzen.
Der Codex-Setup-Aufruf verwendet `mise exec --`, damit auch Task-Unterprozesse
die in `.mise.toml` gepinnten Werkzeuge verwenden.
`task setup:playwright` lädt die Browserdaten separat.
`task doctor` prüft die lokale Toolchain und die virtuelle Umgebung;
`task doctor:playwright` prüft die Browser-Executables separat.
Ein gemeinsamer uv-Cache unter `~/.cache/uv` kann lokale Codex-Läufe
beschleunigen, ist aber keine Projektvoraussetzung.
Persönliche Codex-, IDE- oder Secret-Konfiguration gehört nicht in das
Repository.

`task dev` startet Backend und Frontend parallel.
Das Backend initialisiert die Datenbank über den normalen Migrationspfad; das
Frontend läuft am Entwicklungsproxy unter `http://localhost:4200/`.
Ein Demo-Reset ist ein ausdrücklich getrennter Entwicklungsstart und kein
Seiteneffekt des normalen Servers.

## Testauswahl

| Risiko | Geeigneter Einstieg |
| --- | --- |
| schmale Backend-Regel | betroffener `unittest` unter `backend/tests/` |
| Demo-Vertrag oder -Runtime | betroffener `unittest` unter `demo/tests/` |
| Delivery- oder Workflow-Vertrag | betroffener `unittest` unter `tests/delivery/` |
| Dokumentation und Publikation | betroffener `unittest` unter `tests/docs/` |
| Synthetische Fixtures | `task test:backend` und `task test:demo` |
| Repository-Tooling | betroffener `unittest` unter `tests/tooling/` |
| ausgeliefertes OCI-Image und Compose-Runtimeintegration | `task quality:container` |
| historische v0.6.0-Restore-/Upgradekompatibilität | `task quality:pester` mit `Compatibility.Tests.ps1` |
| reales CLI-Terminal im Produktimage | `task quality:operator-container` |
| Backend im Pull Request | `task quality:backend:pr` |
| Backend vollständig mit Coverage | `task quality:backend` |
| API-, Transport- und Persistenzmodelle | `task backend:typecheck` |
| Backend-Komplexität | `task backend:complexity` |
| Angular-Code | betroffener Vitest-Test, danach `task quality:frontend` |
| produktive npm-Abhängigkeiten | `task quality:security` |
| Go-CLI | `task test:operator` oder `task quality:operator`; für native Archive und bytegleiche Reproduzierbarkeit `task quality:operator-packaging-and-reproducibility`, das den ersten Packaging-Build als Vergleichsbasis nutzt; die beiden Einzeltasks bleiben für gezielte Diagnose verfügbar |
| sichtbarer Browserablauf | `task quality:e2e` |
| Accessibility | `task quality:a11y` getrennt vom E2E-Lauf |
| OCI-/Compose-Smoke, CLI-Terminal oder Kompatibilitätsvertrag | `task quality:container`, `task quality:operator-container` beziehungsweise `task quality:pester` |
| Demo-Liefervertrag | `task quality:demo-deployment` und je nach Änderung `quality:demo` oder `quality:infra` |
| Dokumentation | `task docs:check`, danach `task docs` |
| Erzeugte öffentliche Site und Portal-Links | `task docs:publication:linkcheck` |
| Workflow-/Quality-Evidenzvertrag | `task delivery:test` und `task quality:workflows`; der Vorlauf-Regressionstest startet die echten Selektoraufrufe zusätzlich unter dem Runner-Python vor `setup-python` |
| GitHub-Workflow-Syntax und Expressions | `actionlint` über `task quality:workflows` |
| Zeitabhängige Vulnerability-, Secret- oder externe Linkprüfung | jeweiliger Security-/Linkcheck nach eigener Frequenz; nicht durch Build-Evidenz ersetzen |
| querschnittliche Änderung | `task quality` |

Lokal werden die betroffenen Prüfungen und erforderlichen Integrationsgrenzen
begründet ausgewählt.
Ein Issueabschluss allein verlangt keine zusätzliche vollständige lokale Suite.
Die vollständige finale Abnahme erfolgt in CI am exakten Kandidaten;
vorhandene vollständige Evidenz darf nur nach dem
[Wiederverwendungsvertrag](delivery.md#wiederverwendung-vollständiger-quality-evidenz)
übernommen werden.

Vor Browserprüfungen laufen `mise exec -- task doctor` und
`mise exec -- task doctor:playwright`.

Die öffentliche Pages-Hülle wird mit Hugo Extended und Blowfish v3.6.0 gebaut.
Das eingecheckte Projekt unter `docs/publication/` bindet den vollständigen
Blowfish-Commit `4643c46bd5e921fee51c420575fadebf9f4b3681` über Hugo Modules
ein und verwendet weder `latest` noch einen beweglichen Theme-Branch.
Für eine lokale Vorschau genügt:

```text
task setup:frontend
HUGO_CACHEDIR=/tmp/lzug-hugo-cache task docs:publication
```

Der Theme-Checkout bleibt temporär.
Ein Rückfall auf den letzten konsistenten Pages-Stand erfolgt durch erneuten
Build der dort dokumentierten Repository-Revision mit derselben
Blowfish-Pin; Pages-Dispatch und Deployment bleiben davon getrennte,
manuell freizugebende Schritte.
Jeder Playwright-Lauf verwendet eigene Ports, eine eigene SQLite-Datei unter
`var/e2e/` und synthetische Seed-Daten.
Browser-E2E und Accessibility bleiben getrennte Nachweise; Chromium wird weder
lokal noch in CI mit `--no-sandbox` gestartet.

Ein unverändert auftretender Sandbox-, Browser-, Cache- oder
Container-Engine-Fehler wird als Umgebungsthema dokumentiert.
Er rechtfertigt keine Abschwächung von Produktcode oder Sicherheitsgrenzen.
Die CI ist die finale Abnahme für die ausgewählten Plattform- und
Repositoryverträge.

`task quality:pester` baut zuerst die Produkt- und Migrationsfixture und führt
die gepinnte vollständige Pester-Suite einmal pro Task-Aufrufgraph aus.
Sie enthält den Container-Smoke, den Operator-PTY-Vertrag und den eigenständigen
Kompatibilitätsvertrag.
`quality:container` und `quality:compose` führen nur den Image- und Runtime-Smoke
aus; `quality:operator-container` führt nur den realen PTY-Vertrag aus.
`quality:compose-config` validiert ausschließlich die Compose-Konfiguration.
Die Pull-Request- und Quality-Containerjobs führen reale Containerstarts aus
und bewahren den NUnit-Report unter `build/quality/pester/pester.xml` auf.
Fehlende Engine, fehlendes Image und fehlgeschlagene Readiness sind Fehler;
die Suite kennt keine stillen lokalen Skips.
Nach einem bereits erfolgten Build kann `pwsh -NoProfile -File
scripts/run-pester.ps1` die betroffenen Verträge gezielt erneut ausführen.

Die Pester-Verträge verwenden ausschließlich eindeutige temporäre Compose-
Projekte, Daten-, Socket- und CLI-Artefaktvolumes.
Eigene `LZUG_*`-Deploymentvariablen werden während Compose-Aufrufen isoliert,
damit keine vorhandenen Daten oder Socketpfade ausgewählt werden.
Pester räumt die eigenen Ressourcen auch nach fehlgeschlagenen Assertions auf.
Das unveränderte CLI-Binary läuft sowohl direkt als UID/GID `10001:10001`
im Produktcontainer als auch mit UID/GID `10002:10001` in einem isolierten
Hilfscontainer mit gemeinsamem PID-Namespace und Socketzugriff.
Private age-Dateien und aktuelle Artefakte bleiben in dessen eigenem Volume;
das Backend erhält dieses Volume nicht.
`Operator.Tests.ps1` prüft den interaktiven Einstieg `lzug-admin cli` mit einem
echten Pseudoterminal und dem im Image gebauten Binary.
Native Fehlerdiagnosen nennen Exitcode und verfügbare strukturierte
Fehlerklasse, ohne rohe Antworten, Schlüssel oder Containerlogs auszugeben.
Die konkreten Runtime-, Persistenz- und Upgradegrenzen beschreibt
[Komponenten](components.md#oci-runtime-und-infrastruktur).

`task backend:complexity` gibt den Ruff-C901-Befund für produktive
Backendmodule mit der Schwelle 10 aus.
Der Befund ist zunächst nicht blockierend und wird über `task quality:backend`
auch in der Backend-CI ausgegeben.

Der reguläre Backend-Typcheck verwendet die verbindliche Dateiliste in
`pyproject.toml`.
Sie umfasst die typisierten Anwendungs- und Persistenzgrenzen sowie
`server.py`, `healthcheck.py`, `build_metadata.py`, `security.py`, `runtime.py`,
`admin_socket.py` und `admin_socket_artifacts.py`.
Der Aufruf erfolgt als Teil von `task quality:backend:pr` beziehungsweise
`task quality:backend`.

## Dependencies und Dependabot

Python-Abhängigkeiten werden mit `uv add` und anschließendem gelocktem Sync
geändert; Frontend-Abhängigkeiten verwenden npm und
`frontend/package-lock.json`.
Das Go-Modul bleibt über `operator-cli/go.mod` und `operator-cli/go.sum`
reproduzierbar.
Eine Änderung an Runtime, Lockfile, Toolchain oder Workflow benötigt die
betroffenen Audits, Builds und Vertragstests und in der Regel den breiten
Qualitätspfad.

Dependabot prüft Go-Module, uv, npm und GitHub Actions wöchentlich.
Routineupdates werden in `.github/dependabot.yml` nach technischem Ökosystem
und, bei npm, nach den bekannten Angular-, Taiga-UI-, Linting- und Vitest-
Familien gebündelt.
Version- und Sicherheitsgruppen bleiben getrennt;
Majorupdates bleiben außerhalb der Routinegruppen und damit manuell.
Eine neue Gruppierungsregel ändert bereits offene Einzel-Pull-Requests nicht
rückwirkend.
Ein Einzel-PR wird deshalb erst geschlossen, wenn ein sichtbarer erfolgreicher
Gruppen-PR dieselbe Aktualisierung vollständig ersetzt.

Nur eindeutig klassifizierte uv- oder npm-Patch-/Minor-Updates dürfen durch
den vorgesehenen Workflow für Squash-Auto-Merge angemeldet werden.
Major-, GitHub-Actions-, konfliktäre und nicht eindeutig klassifizierte
Updates bleiben manuell.
Der `pull_request_target`-Workflow checkt keinen Pull-Request-Code aus und führt
nur verifizierte Dependabot-Metadaten gegen das normale Ruleset aus.

## Synthetische Fixtures

`fixtures/synthetic-fixtures.json` ist die kanonische Quelle für gemeinsame
Demo- und Testidentitäten.
Der versionierte Katalog verwendet Figuren und Motive aus William Shakespeares
„Ein Sommernachtstraum“ und trennt den Hauptausschuss Athen vom Fremdausschuss
Feenwald.
Beide Kammern, sämtliche Personen, Kontakte und Prüfungsvorgänge sind
ausdrücklich fiktiv.
Die drei Athener Demo-Orte verwenden ausschließlich die im Katalog bezeichneten
realen Anschriften, Orientierungen und Referenzkoordinaten.
Prüfungsstätten, Räume, Kapazitäten, Barrierefreiheitsbewertungen, Kontakte und
fachliche Zuordnungen bleiben sichtbar synthetisch und behaupten keine
Kooperation mit den realen Orten.

Jede sichtbare Entität besitzt einen stabilen Schlüssel unter
`name.papaspyrou.repertoire.lzug.fixture`.
Personen, Mitgliedschaften und fachliche Datenbank-IDs bleiben getrennt;
Lookup und Szenariozuordnung erfolgen über den semantischen Schlüssel.
Orte, Räume und Ortskontakte besitzen eigene Schlüssel und technische IDs.
Die `legacy_mapping` erhält vorhandene technische IDs bei der Umstellung;
Anzeigenamen dienen nie als Identität oder Verknüpfung.
Die Abdeckungsmatrix im Katalog weist Vorsitz, Stellvertretung, alle
Vertreterseiten, reguläre und stellvertretende Mitglieder, Fallback,
Ersatzperson, Mehrfachmitgliedschaft, Prüflinge, Fremdausschuss sowie positive
und negative Autorisierungspfade einschließlich der beiden #487-Szenarien aus.

Synthetische E-Mail-Adressen verwenden ausschließlich
`@demo.lzug.invalid`; Telefonnummern sind nicht belegt.
Jede reale Ortsreferenz enthält eine kanonische HTTPS-Quelle und das feste
Abrufdatum `2026-09-01`.
Die zuständigen Python-Komponenten bilden den Katalog zur Laufzeit in
disposable SQL-Seeds und Testdaten ab.
Das Frontend lädt die kanonische JSON-Quelle direkt.
Die Profile `development` und `public-demo` stehen deklarativ im Katalog.
Es gibt keine generierten sprachspezifischen Fixture-Kopien und keinen
separaten Fixture-Compiler.

Der Demo-Artefaktbau kompiliert den Public-Demo-Seed aus Katalog und Profil
und schreibt nur die daraus erzeugte Datenbank in das Seed-Image.
Die vollständigen Zustände einschließlich der beiden #487-Szenarien liegen
deklarativ im Katalog.
Ein Besucher-Arbeitsstand wird zur Laufzeit ausschließlich aus diesem Seed
kopiert und beim Reset erneut daraus hergestellt.
`demo.tests.test_demo_runtime` prüft beide Reihenfolgen, Rollen- und
Allowlist-Grenzen, Benachrichtigungs- und Kalenderfolgen, Isolation, Ablauf und
Reset.
Katalogversion, Katalogrevision und Demo-Matrixversion sind an das
inhaltsadressierte Seed-Manifest gebunden; eine unpassende Kombination
verhindert den Demo-Start.
Die Katalogvalidierung ist Teil der zuständigen Backend- und Demo-Tests.
Eine Veröffentlichung des geänderten sichtbaren Demo-Inhalts und des daraus
entstehenden Deployment-Digests setzt die Freigabe des konkreten Stands oder
eine Delta-Freigabe nach #584 voraus.
Diese Fixture-Umstellung erteilt selbst keine Freigabe und stößt keinen Release
an.

## Dokumentation bearbeiten

Jede Information hat eine primäre Zielgruppe, genau eine Dokumentart und eine
kanonische Quelle.
Fachliche, Nutzungs- und Betreiberanleitungen liegen im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki); aktuelle technische Orientierung in Einstieg plus fünf Kernbereichen; langfristige
Entscheidungen in ADRs; ausführbare API-, Daten-, Qualitäts- und
Releaseverträge in Code und deklarativen Quellen.

Eigene gepflegte Markdown-Prosa verwendet Semantic Line Breaks.
Jeder Satz und jede sinnvolle Gedankeneinheit beginnt in einer neuen Quellzeile.
Tabellen, Listenstruktur, Codeblöcke, Front Matter, URLs und technische
Zeichenketten bleiben unverändert.
Drittmaterial, Lizenztexte und generierte Inhalte werden nicht rein
redaktionell umgebrochen.

Architekturdiagramme liegen als portable Mermaid-Codeblöcke in der zuständigen
Seite.
C4-orientierte Sichten verwenden stabile `flowchart`-Syntax, Abläufe
`sequenceDiagram`; separat erzeugte Bildkopien und experimentelle C4-Grammatik
werden nicht gepflegt.

Ein ADR ist für eine langfristige technische Entscheidung mit relevanten
Alternativen erforderlich, nicht für lokale Implementierungsdetails,
Projektplanung oder erledigte Schritte.
Nummer, Nygard-Struktur, Status und beidseitige Ersetzungsmarker folgen dem
[ADR-Register](decisions/index.md) und `decisions/TEMPLATE.md`.
Akzeptierte ADRs werden nicht nachträglich inhaltlich umgeschrieben.

Öffentliche Python-APIs verwenden Google-Style-Docstrings, exportierte
TypeScript-Services, Modelle und fachliche Komponenten TSDoc.
Kommentare erklären Invarianten, Ownership, Seiteneffekte und Fehlergrenzen,
nicht triviale Typangaben oder eine zweite OpenAPI-Fassung.

`task docs:check` erzwingt die flache Entwicklerstruktur, die aktive Navigation,
ADR-Register und Ersetzungssemantik, das Verbot eines Ersatzarchivs sowie den
Ausschluss offensichtlicher Planungs-, Routen- und Schema-Zweitlisten.
`task docs` ergänzt den strikten MkDocs- und TypeDoc-Build.
Der öffentliche Referenzaufbau folgt dem Repository-Vertrag unter
[Delivery und Veröffentlichung](delivery.md).

## Review

Reviews ergänzen deterministische Prüfungen und bewerten Architektur,
Wartbarkeit, Teststrategie, Dokumentation, fachliche Konsistenz,
Betriebsfähigkeit, Abhängigkeiten und UX.
Sie erfinden keine fachlichen Regeln und behaupten ohne Evidenz keinen
produktiven Betriebszustand.

Ein belastbarer Befund nennt Fundstelle oder Evidenz, Problem, Auswirkung,
Priorität, Handlungsempfehlung und Unsicherheit.
Automatisierte Accessibility-Prüfung belegt nicht automatisch verständliche
Informationshierarchie oder vollständige WCAG-Konformität.
Sichtbare Änderungen werden zusätzlich auf Begriffe, Aktionsgewichtung,
Laden, Leerzustand, Erfolg, Fehler, Bestätigung, Abbruch, Desktop, Mobil,
Kontrast und Fokus geprüft.

Bestätigte Befunde werden in GitHub Issues nachverfolgt.
`review:*`-Labels klassifizieren nur den Gegenstand, nicht Autorenschaft,
Bestätigung, Priorität, Status oder Mergefreigabe.
Eine langfristige Richtungsänderung benötigt gegebenenfalls einen ADR; eine
lokale Korrektur nicht.

## Aufträge und Zuständigkeiten

Issues enthalten Ziel, Umfang und Akzeptanzkriterien.
Für Coding Agents gelten die Projektregeln in `AGENTS.md`;
ein umsetzungsreifes Issue allein ist für sie noch keine Beauftragung.
Persönliche Skills ergänzen das Verfahren, sind aber keine Projektvoraussetzung.
Review- und Umsetzungsnachweise werden an den zugehörigen GitHub-Artefakten
festgehalten.

## Pull Request und Closeout

Änderungen folgen einem GitHub Issue und werden auf einem eigenen Branch
eingereicht.
Der [Beitragsleitfaden](https://github.com/lxndrp/lzug/blob/master/CONTRIBUTING.md) nennt
Verknüpfung, Metadaten und Reviewvoraussetzungen.
`task pr:create` prüft die schließende oder ausdrücklich nicht schließende
Issue-Verknüpfung und ordnet den Pull Request dem Project zu.
Nach Änderungen werden die betroffenen Prüfungen und die CI am neuen Commit
erneut bewertet.
Merge, Release und Veröffentlichung bleiben getrennte Maintainerentscheidungen;
der [Delivery-Vertrag](delivery.md) beschreibt die technischen Gates.
