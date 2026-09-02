# Entwicklung

[`CONTRIBUTING.md`](https://github.com/lxndrp/lzug/blob/master/CONTRIBUTING.md)
enthält die verbindlichen Beitragsregeln.
Das [GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung) führt Menschen
durch Einrichtung und täglichen Arbeitsprozess.
Diese Seite bündelt die revisionsgebundenen technischen Einstiege und kopiert
weder Issue-Prozess noch Wiki-Anleitungen vollständig.

## Toolchain und Einrichtung

`mise` stellt die projektweit gepinnten Werkzeuge bereit.
Der aktuelle Stand verwendet Python 3.14.6, Node.js 26.5.0, Go 1.26.5,
Task 3.52.0, GoReleaser 2.17.1, Syft 1.51.0, OpenTofu 1.12.5 und
Hugo Extended 0.165.0; `.mise.toml` und die jeweiligen Versionsdateien bleiben
maßgeblich.
`uv.lock`, `frontend/package-lock.json` und `go.sum` binden die
Abhängigkeiten.

```sh
mise install
task setup
task doctor
```

`task setup` erzeugt `.venv`, synchronisiert die gelockten Python-Pakete,
installiert das Frontend mit `npm ci` und lädt Playwright Chromium.
`task doctor` prüft die lokale Toolchain, den gemeinsamen uv-Cache unter
`~/.cache/uv`, die virtuelle Umgebung und die Browser-Executable.
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
| schmale Python-Regel | betroffener `unittest` unter `backend/tests/` |
| Backend insgesamt | `task quality:backend` |
| API-, Transport- und Persistenzmodelle | `task backend:typecheck` |
| Backend-Komplexität | `task backend:complexity` |
| Angular-Code | betroffener Vitest-Test, danach `task quality:frontend` |
| produktive npm-Abhängigkeiten | `task quality:security` |
| Go-CLI | `task test:operator` oder `task quality:operator` |
| sichtbarer Browserablauf | `task quality:e2e` |
| Accessibility | `task quality:a11y` getrennt vom E2E-Lauf |
| OCI, Compose oder CLI-Container | der passende `task quality:container`, `quality:compose` oder `quality:operator-container` |
| Demo-Liefervertrag | `task quality:demo-deployment` und je nach Änderung `quality:demo` oder `quality:infra` |
| Dokumentation | `task docs:check`, danach `task docs` |
| querschnittliche Änderung | `task quality` |

Vor Browserprüfungen läuft `task doctor`.
Jeder Playwright-Lauf verwendet eigene Ports, eine eigene SQLite-Datei unter
`var/e2e/` und synthetische Seed-Daten.
Browser-E2E und Accessibility bleiben getrennte Nachweise; Chromium wird weder
lokal noch in CI mit `--no-sandbox` gestartet.

Ein unverändert auftretender Sandbox-, Browser-, Cache- oder
Container-Engine-Fehler wird als Umgebungsthema dokumentiert.
Er rechtfertigt keine Abschwächung von Produktcode oder Sicherheitsgrenzen.
Die CI ist die finale Abnahme für die ausgewählten Plattform- und
Repositoryverträge.

`task backend:complexity` gibt den Ruff-C901-Befund für produktive
Backendmodule mit der Schwelle 10 aus.
Der Befund ist zunächst nicht blockierend und wird über `task quality:backend`
auch in der Backend-CI ausgegeben.

## Dependencies und Dependabot

Python-Abhängigkeiten werden mit `uv add` und anschließendem gelocktem Sync
geändert; Frontend-Abhängigkeiten verwenden npm und
`frontend/package-lock.json`.
Go-Module bleiben über `go.mod` und `go.sum` reproduzierbar.
Eine Änderung an Runtime, Lockfile, Toolchain oder Workflow benötigt die
betroffenen Audits, Builds und Vertragstests und in der Regel den breiten
Qualitätspfad.

Dependabot prüft Go-Module, uv, npm und GitHub Actions wöchentlich.
Die Go-Erweiterungsmodule, Angular, Taiga UI, Frontend-Linting, Vitest und
CodeQL werden in ihren in
`.github/dependabot.yml` definierten technischen Familien gebündelt;
Version- und Sicherheitsgruppen bleiben getrennt.
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
`scripts/generate_synthetic_fixtures.py` erzeugt daraus SQL-, Angular- und
Prototypadapter sowie den Python-Adapter für Demo-Rollen und semantische IDs.
Generierte Dateien werden nicht direkt bearbeitet.

```sh
python3 scripts/generate_synthetic_fixtures.py
task fixtures:check
```

Der Demo-Artefaktbau ergänzt fachlich gezielte synthetische Zustände für
Protokoll, Bewertung, Abschluss, Wiederöffnung und Reset.
Die isolierten Szenarien aus #487 werden dagegen beim Start eines
Besucher-Arbeitsstands relativ zur aktuellen Instanzzeit erzeugt.
`backend.tests.test_demo_runtime` prüft beide Reihenfolgen, Rollen- und
Allowlist-Grenzen, Benachrichtigungs- und Kalenderfolgen, Isolation, Ablauf und
Reset.
Katalogversion, Katalogrevision und Demo-Matrixversion sind an das
inhaltsadressierte Seed-Manifest gebunden; eine unpassende Kombination
verhindert den Demo-Start.
Der Driftcheck ist Teil von Pull-Request-Auswahl und `task quality` und weist
manuelle Änderungen an jedem generierten Adapter zurück.
Eine Veröffentlichung des geänderten sichtbaren Demo-Inhalts und des daraus
entstehenden Deployment-Digests setzt die Freigabe des konkreten Stands oder
eine Delta-Freigabe nach #584 voraus.
Diese Fixture-Umstellung erteilt selbst keine Freigabe und stößt keinen Release
an.

## Dokumentation bearbeiten

Jede Information hat eine primäre Zielgruppe, genau eine Dokumentart und eine
kanonische Quelle.
Fachliche, Nutzungs- und Betreiberanleitungen liegen im Wiki; aktuelle
technische Orientierung in Einstieg plus fünf Kernbereichen; langfristige
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
Der öffentliche Referenzaufbau und das Wiki bleiben getrennte Verträge unter
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

## Pull Request und Closeout

Issue-Arbeit entsteht auf dem issuebezogenen Branch und Worktree.
Vor dem Pull Request werden Assignees, Milestone und Project des Issues live
gelesen.
`task pr:create` prüft die exakte `Closes #<nummer>`- oder ausdrücklich
gewählte `Tracks #<nummer>`-Zeile, übernimmt nur gesetzte Metadaten und ordnet
den Pull Request dem Project `lzug Roadmap` zu.

Nach dem Erstellen werden schließende Verknüpfung, Assignees, Milestone und
Project mit `gh pr view` verifiziert.
Nach jeder inhaltlichen Änderung laufen die betroffenen lokalen Prüfungen und
die CI des neuen Commits erneut.
Vor dem Merge werden allgemeine Kommentare, Review-Threads,
Security-Audits, Code-Scanning- und automatisierte PR-Hinweise vollständig
geprüft und sinnvolle Befunde vor dem Auflösen umgesetzt.

Merge, Release, Workflow-Dispatch und externe Aktivierung bleiben getrennte
Maintainerentscheidungen.
Nach einem freigegebenen Merge werden Post-Merge-Qualität, Issue- und
Project-Status live geprüft.
Vor dem Entfernen des issuebezogenen Worktrees muss er sauber sein; nur der
zugehörige lokale und Remote-Feature-Branch wird entfernt.
