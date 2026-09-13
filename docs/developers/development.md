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
| schmale Backend-Regel | betroffener `unittest` unter `backend/tests/` |
| Demo-Vertrag oder -Runtime | betroffener `unittest` unter `demo/tests/` |
| Delivery- oder Workflow-Vertrag | betroffener `unittest` unter `tests/delivery/` |
| Dokumentation und Publikation | betroffener `unittest` unter `tests/docs/` |
| Synthetische Fixtures | `task test:fixtures` oder `task fixtures:check` |
| Repository-Tooling | betroffener `unittest` unter `tests/tooling/` |
| OCI- oder Compose-Regel | betroffener `unittest` unter `tests/oci/` |
| Backend im Pull Request | `task quality:backend:pr` |
| Backend vollständig mit Coverage | `task quality:backend` |
| API-, Transport- und Persistenzmodelle | `task backend:typecheck` |
| Backend-Komplexität | `task backend:complexity` |
| Angular-Code | betroffener Vitest-Test, danach `task quality:frontend` |
| produktive npm-Abhängigkeiten | `task quality:security` |
| Go-CLI | `task test:operator` oder `task quality:operator`; für native Archive zusätzlich `task quality:operator-packaging` |
| sichtbarer Browserablauf | `task quality:e2e` |
| Accessibility | `task quality:a11y` getrennt vom E2E-Lauf |
| OCI, Compose oder CLI-Container | der passende `task quality:container`, `quality:compose` oder `quality:operator-container` |
| Demo-Liefervertrag | `task quality:demo-deployment` und je nach Änderung `quality:demo` oder `quality:infra` |
| Dokumentation | `task docs:check`, danach `task docs` |
| Erzeugte öffentliche Site und Portal-Links | `task docs:publication:linkcheck` |
| querschnittliche Änderung | `task quality` |

Vor Browserprüfungen läuft `task doctor`.

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

`task backend:complexity` gibt den Ruff-C901-Befund für produktive
Backendmodule mit der Schwelle 10 aus.
Der Befund ist zunächst nicht blockierend und wird über `task quality:backend`
auch in der Backend-CI ausgegeben.

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
`fixtures/generate.py` ist der einzige Fixture-Compiler.
Er erzeugt den Entwicklungsseed und den vollständigen Public-Demo-Seed als
disposable SQL-Buildartefakte sowie den Angular-Testadapter.
Die Profile `development` und `public-demo` stehen deklarativ im Katalog.
Generierte Dateien werden nicht direkt bearbeitet.

```sh
python3 fixtures/generate.py
task fixtures:check
```

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

Übergaben zwischen Codex-Tasks sind asynchrone Aufträge.
Der Link zum maßgeblichen Issue oder Pull Request und die dafür notwendigen
neuen Angaben genügen;
Empfangsbestätigung, Rückversicherungsrunde und Kontrolle des Empfänger-Tasks
durch den Sender entfallen.
Die Zustellung belegt nicht die Umsetzung, deren Stand ausschließlich an den
GitHub-Artefakten abgelesen wird.
Fehlgeschlagene Zustellungen werden gezielt behandelt und unklare vor einer
Wiederholung geklärt.

| Schritt | Zuständigkeit |
| --- | --- |
| koordinierter Start | `Weiterentwicklung koordinieren` prüft Reife, Review-Gate und Complexity einmal; der Issue-Task übernimmt diese Evidenz. |
| direkter Start | Der Issue-Task führt die sonst fehlende Startprüfung einmal durch. |
| Umsetzung | Der Issue-Task bearbeitet Code, Tests, Pull Request und neue Reviewbefunde. |
| Merge und lokaler Closeout | `Weiterentwicklung koordinieren` handelt erst nach der jeweiligen Maintainer-Freigabe. |
| Istwerte und Planung | `Projektplan aktualisieren` übernimmt belegte Goal-Werte und bestätigte Planänderungen. |

Ein Task dokumentiert seinen Abschluss am maßgeblichen GitHub-Artefakt.
Nur ein tatsächlich nötiger Folgeschritt wird genau einmal an den dafür
zuständigen Task übergeben;
eine Berichtskette durch vorherige Tasks entsteht nicht.
Rückfragen bleiben auf unklare Entscheidungen, fehlende Berechtigungen,
Blocker und begründete Modellhochstufungen beschränkt.
Codeprüfung, CI und menschlicher Review bleiben eigenständige fachliche
Prüfungen und werden weder durch Übergaben noch durch administrative Abgleiche
ersetzt.

## Codex-Goals und Milestone-Reviews

Jede temporäre Issue-Umsetzung verwendet ein eigenes Codex-Goal.
Eine klar beschriebene Umsetzung startet mit Luna und medium.
Complexity bleibt Planungsmetadatum und steuert die Prüfung, nicht automatisch
Modell oder Reasoning.
Eine Hochstufung wird bei fachlicher Unsicherheit oder einem wiederholten
inhaltlichen Fehlversuch knapp mit Grund und Vorschlag beim Nutzer angefragt;
Sandboxfehler, Berechtigungen und CI-Wartezeit lösen keine Eskalation aus.
Nach tatsächlich erreichtem Ziel liefert dessen finaler Status die belegbare
Laufzeit in Sekunden und, sofern technisch verfügbar, den Tokenverbrauch.
`Projektplan aktualisieren` überträgt die Laufzeit als Stundenwert in
`Factual effort (h)` und die unveränderte Tokenzahl in `Cost (Tokens)`.
Ein fehlender Einzelwert lässt genau dieses Feld leer;
ohne Goal-Nachweis bleiben beide Felder leer.
Historische Zeitspannen, Chat-Zeitstempel und Schätzungen ersetzen keine
Goal-Metrik.

Vor der ersten regulären Umsetzung jedes neuen SemVer-Milestones prüft
`Codebasis reviewen` den vollständigen aktuellen Stand von `master`.
Ein geschlossener, demselben Milestone zugeordneter Review-Anker dokumentiert
mindestens die geprüfte Commit-SHA, den Umfang, den Abschluss und die
verknüpften Befunde.
Der Anker ist ein `type: task` ohne `review:`-Label;
bestätigte Befunde erhalten eigene präzise Issues und nur die jeweils
zutreffenden `review:`-Labels.
Ohne diesen Nachweis bleibt die erste reguläre Umsetzung gesperrt.
Planungsfelder und Project-README werden aus dem Review oder den Goal-Metriken
nur geändert, wenn ein belegbarer Planungsbedarf besteht und die Änderung
bestätigt ist.

Die folgenden Szenarien bilden die Prozessprüfung:

| Szenario | Erwartetes Ergebnis |
| --- | --- |
| Goal weist Laufzeit und Tokenzahl aus | Beide Project-Felder werden aus genau diesen Werten gepflegt. |
| Goal weist nur eine Metrik aus | Nur das zugehörige Project-Feld wird gepflegt; das andere bleibt leer. |
| Goal weist keine Metrik aus | Beide Project-Felder bleiben leer; es erfolgt keine Schätzung. |
| Erster regulärer Auftrag eines SemVer-Milestones ohne abgeschlossenen Review-Anker | Die Umsetzung bleibt blockiert, bis `Codebasis reviewen` den vollständigen Review dokumentiert hat. |
| Abgeschlossener Review-Anker für den SemVer-Milestone | Die reguläre Umsetzung darf nach den übrigen Reifeprüfungen mit dem schlanken Standard beginnen; Befunde werden über eigene Issues geplant. |
| Fachliche Unsicherheit oder wiederholter inhaltlicher Fehlversuch | Der Umsetzungstask fragt einmalig nach Freigabe einer begründeten Modell-/Reasoning-Hochstufung; ein automatischer Wechsel erfolgt nicht. |
| Eindeutige erfolgreiche reversible Operation | Die Werkzeugantwort genügt; eine unabhängige Zweitprüfung erfolgt nicht. |
| Neuer Commit, neuer Befund oder relevante Umweltänderung | Nur die dadurch betroffene Prüfung wird aktualisiert. |

## Pull Request und Closeout

Issue-Arbeit entsteht auf dem issuebezogenen Branch und Worktree.
Complexity und Profil werden nicht routinemäßig in den Pull Request kopiert;
nur wesentliche Modellabweichungen oder Eskalationen werden einmal benannt.
Der Issue-Task liest Assignees, Milestone und Project-Zuordnung unmittelbar vor
dem Pull Request einmal.
`task pr:create` prüft die exakte `Closes #<nummer>`- oder ausdrücklich
gewählte `Tracks #<nummer>`-Zeile, übernimmt die gesetzten Werte und ordnet den
Pull Request dem Project `lzug Roadmap` zu.
Eine eindeutige erfolgreiche Werkzeugantwort benötigt keine zusätzliche
Metadatenprüfung;
nur bei Lücke, Widerspruch oder relevanter Änderung wird gezielt nachgelesen.
Nach jeder inhaltlichen Änderung laufen die betroffenen lokalen Prüfungen und
die CI des neuen Commits erneut.
Vor dem Merge werden allgemeine Kommentare, Review-Threads,
Security-Audits, Code-Scanning- und automatisierte PR-Hinweise vollständig
geprüft und sinnvolle Befunde vor dem Auflösen umgesetzt.

Merge, Release, Workflow-Dispatch und externe Aktivierung bleiben getrennte
Maintainerentscheidungen.
`Weiterentwicklung koordinieren` führt einen freigegebenen Merge und danach den
lokalen Closeout aus.
Vor dem Entfernen des issuebezogenen Worktrees prüft die Koordination lokale
und ignorierte Daten;
bei Resten stoppt sie ohne Verwerfen oder Sichern.
Nur ein sauberer zugehöriger Worktree sowie sein lokaler und Remote-Feature-
Branch werden entfernt;
der Umsetzungstask wird nicht automatisch archiviert.

Am Iterationsende und vor Release-Abschluss erfolgt ein ereignisgesteuerter
Sammelabgleich, bei zusammenfallenden Anlässen nur einmal.
Er ist Teil des bestehenden Closeouts und kein zeitgesteuerter Scheduler.
Die Koordination bearbeitet offene Pull-Request-, CI- und Closeout-Reste sowie
verwaiste Issue-Arbeitsbereiche und bündelt unklare Lücken.
Ein einzelner Sammelauftrag an `Projektplan aktualisieren` prüft abgeschlossene
Issues auf Project-Zuordnung, Status, vorhandene Istwerte und daraus folgende
Planungs- oder Project-README-Abweichungen.
Eindeutig belegte Routinekorrekturen erfolgen im bestehenden Auftrag;
Goal-Werte werden nicht doppelt gezählt, fehlende Werte nicht erfunden und
Planänderungen weiterhin nur nach bestätigter Entscheidung vorgenommen.
