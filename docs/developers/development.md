# Entwicklung

[`CONTRIBUTING.md`](https://github.com/lxndrp/lzug/blob/master/CONTRIBUTING.md)
enthält die verbindlichen Beitragsregeln.
Diese Seite zeigt den lokalen Einstieg, die Auswahl passender Prüfungen und die
Regeln für Änderungen an Abhängigkeiten und Dokumentation.
Komponentenverträge stehen unter [Komponenten](components.md), CI- und
Publikationsnachweise unter [Delivery und Veröffentlichung](delivery.md).

## Toolchain und Einrichtung

`mise` stellt die Werkzeuge aus `.mise.toml` bereit;
die Abhängigkeiten bleiben in den jeweiligen Ökosystem-Lockdateien gebunden.
Die Aufgaben und ihre Befehle stehen in `Taskfile.yml`.
Die Zuständigkeit dieser Quellen erläutert [ADR-0034](decisions/0034-versionsbindung-und-unveraenderliche-referenzen.md).

Die allgemeine Zuständigkeitsregel und Entscheidungsreihenfolge beschreibt
[ADR-0039](decisions/0039-deklarative-toolchain-zustaendigkeiten.md): zuerst
native deklarative Konfiguration und Standardmechanismen nutzen, danach
verbleibende Logik nach Verantwortung, Sprache und Ablageort zuordnen.
`mise` besitzt Werkzeugversionen und Umgebung, Paketmanager ihre Abhängigkeiten,
Task den gemeinsamen Ablaufgraph und GitHub Actions die Plattformaufgaben.
Komponentenlogik bleibt in der Codebase und Sprache der Komponente;
notwendiges komponentenübergreifendes oder allgemeines Repository-Skripting
liegt in PowerShell.
Eine pauschale Python-Ausschlussregel oder eine Pflicht zur Umschreibung
bestehender Komponentenlogik gilt nicht.

Stabile Policy gehört in die native Werkzeugkonfiguration; konkrete Ziele,
Ausgaben und laufbezogene Parameter bleiben am jeweiligen Aufruf sichtbar.
`.syft.yaml` und der native Backend-OpenAPI-Export zeigen diese Trennung.
Eine Sprachüberführung oder das Verschieben generischer Orchestrierung allein
belegt keine Vereinfachung.

```sh
mise install
mise exec -- task setup
mise exec -- task doctor
```

`task setup` richtet Backend- und Frontend-Abhängigkeiten ein.
Für Browserprüfungen werden die Playwright-Browser separat installiert und geprüft:

```sh
mise exec -- task setup:playwright
mise exec -- task doctor:playwright
```

`mise exec --` stellt auch für Task-Unterprozesse die projektweit gewählten
Werkzeuge bereit.
`task dev` startet Backend und Frontend; das Frontend ist über
`http://localhost:4200/` erreichbar.
Die Datenbank wird über den normalen Migrationspfad vorbereitet.
Ein Demo-Reset ist ein eigener Vorgang und kein Seiteneffekt des Entwicklungsstarts.
Weitere Befehle und ihre Beschreibung zeigt `mise exec -- task --list`.

## Testauswahl

Beginne mit der kleinsten Prüfung, die die geänderte Grenze tatsächlich belegt.
Bei Änderungen an Toolchain, Abhängigkeiten, CI, Sicherheitsgrenzen oder mehreren
Komponenten läuft zusätzlich `task quality`.
Die CI prüft den exakten Pull-Request-Stand und bleibt die finale Abnahme.
Der [Delivery-Vertrag](delivery.md#pull-request-gates) beschreibt die Auswahl
der CI-Gates; [vollständige Quality-Evidenz](delivery.md)
wird dort an eine feste Revision und vollständige Artefakte gebunden.

| Änderung | Lokaler Einstieg |
| --- | --- |
| Backend | Betroffener Test unter `backend/tests/`, danach `task quality:backend:pr` bei breiterer Änderung |
| Frontend oder API-Transport | Betroffener Vitest-Test, `task quality:frontend` und bei Vertragsänderung `task quality:frontend-transport` |
| Betreiber-CLI | `task test:operator`, bei Packaging-Änderung `task quality:operator-packaging-and-reproducibility` |
| Demo oder synthetische Fixtures | Betroffene Tests unter `demo/tests/` oder `backend/tests/`, danach `task quality:demo` bei Runtime-Änderung |
| Delivery, OCI oder Compose | Betroffener Test unter `tests/delivery/` oder `tests/pester/`; passende `quality:*`-Task für die reale Integrationsgrenze |
| Dokumentation und Site | `task docs:check`, `task docs`; für öffentliche Seiten zusätzlich die passenden `docs:publication:*`-Tasks |
| Infrastruktur | `task quality:infra` |
| Sichtbarer Browserablauf | `task quality:e2e` und getrennt `task quality:a11y`; vorher `task doctor` und `task doctor:playwright` |

Die vollständige Taskliste mit Beschreibungen steht im Taskfile und unter
`task --list`.
Browserläufe verwenden isolierte Testdaten; E2E und Accessibility sind getrennte
Nachweise.
Chromium wird weder lokal noch in CI mit `--no-sandbox` gestartet.
Ein unverändert auftretender Sandbox- oder Container-Engine-Fehler wird als
Umgebungsthema eingeordnet und rechtfertigt keine Abschwächung des Produktcodes.

## Abhängigkeiten ändern

Python-Abhängigkeiten werden mit `uv add` und aktualisierter `uv.lock`
gepflegt, Frontend-Abhängigkeiten mit npm und
`frontend/package-lock.json`, Go-Abhängigkeiten mit dem Go-Modul und
`operator-cli/go.sum`.
Versionen der projektweiten Werkzeuge gehören in `.mise.toml`.
Nach Änderungen an Runtime, Lockdateien, Toolchain oder Workflow die betroffenen
Audits, Builds und Vertragstests ausführen; in der Regel ist `task quality`
angebracht.
Die automatische Update-Gruppierung steht in `.github/dependabot.yml`,
die Mergegrenze in `AGENTS.md`.

## Synthetische Fixtures

`fixtures/synthetic-fixtures.json`
ist die kanonische Quelle für gemeinsame Demo- und Testdaten.
Personen, Ausschüsse und Prüfungsvorgänge sind fiktiv; nur ausdrücklich
gekennzeichnete Ortsreferenzen beziehen sich auf reale Orte.
Entitäten werden über stabile semantische Schlüssel statt Anzeigenamen
zugeordnet.
Die Profile `development` und `public-demo` stehen im Katalog;
Backend und Demo erzeugen daraus ihre Test- und Seed-Daten, während das
Frontend die JSON-Quelle direkt nutzt.
Es werden keine sprachspezifischen Fixture-Kopien gepflegt.
Änderungen am Katalog mit `backend/tests/test_synthetic_fixtures.py` und den
betroffenen Demo-Tests prüfen.
Eine Veröffentlichung geänderter Demo-Inhalte ist ein gesondert freizugebender
[Delivery-Schritt](delivery.md#demo-promotion-und-deployment).

## Dokumentation bearbeiten

Jede Information hat eine primäre Zielgruppe und eine kanonische Quelle:
fachliche, Nutzungs- und Betreiberanleitungen liegen im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki), technische Orientierung
im Entwicklerhandbuch und langfristige Entscheidungen in ADRs.
Ausführbare API-, Daten-, Qualitäts- und Releaseverträge bleiben in Code und
deklarativen Quellen.
Der [Entwicklereinstieg](index.md) zeigt die maßgeblichen Quellen.

Eigene gepflegte Markdown-Prosa verwendet Semantic Line Breaks:
Jeder Satz und jede sinnvolle Gedankeneinheit beginnt in einer neuen Quellzeile.
Tabellen, Listenstruktur, Codeblöcke, Front Matter, URLs und technische
Zeichenketten bleiben unverändert.
Drittmaterial, Lizenztexte und generierte Inhalte werden nicht rein
redaktionell umgebrochen.

Architekturdiagramme liegen als Mermaid-Codeblöcke auf der zuständigen Seite.
Langfristige technische Entscheidungen mit relevanten Alternativen erhalten
einen ADR nach [Register und Vorlage](decisions/index.md).
Akzeptierte ADRs werden nicht nachträglich inhaltlich umgeschrieben.
Öffentliche Python-APIs verwenden Google-Style-Docstrings, exportierte
TypeScript-Services und fachliche Komponenten TSDoc.
Kommentare erklären Invarianten, Ownership, Seiteneffekte und Fehlergrenzen.

`task docs:check` prüft die Projektstruktur und das ADR-Register;
`task docs` baut zusätzlich die technischen Referenzen.
Für die öffentliche Site baut `task docs:publication` ein lokales Artefakt,
ohne es zu veröffentlichen.
Build, Link-, Browser- und Accessibility-Nachweise sowie die manuelle
Publikationsgrenze beschreibt [Delivery und Veröffentlichung](delivery.md).

## Review

Reviews ergänzen Tests und statische Prüfungen um Architektur, Wartbarkeit,
fachliche Konsistenz, Bedienbarkeit und Betrieb.
Ein Befund nennt Fundstelle, Auswirkung, Priorität und Unsicherheit;
bestätigte Befunde werden nach Duplikatprüfung in GitHub Issues verfolgt.
`review:*`-Labels klassifizieren den Gegenstand, nicht Status oder Freigabe.
Bei sichtbaren Änderungen zusätzlich Zustände, Mobilansicht, Kontrast und
Tastaturfokus prüfen.
Automatisierte Accessibility-Prüfungen belegen keine vollständige
WCAG-Konformität.

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
