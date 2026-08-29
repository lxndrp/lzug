# Dokumentation und Architekturentscheidungen

Produkt-, Fach- und Architekturdokumentation ist auf Deutsch; Code-Kommentare
sind Englisch. Jede Information hat eine primäre Zielgruppe, genau eine
Dokumentart und eine kanonische Quelle. Planung, Prioritäten, Abhängigkeiten
und Liefertermine gehören in GitHub Issues und das Roadmap-Project, nicht in
ADRs oder Runbooks.

Das öffentliche redaktionelle Handbuch liegt ausschließlich im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki). Die Dateien unter `docs/`
sind die technische Quellbasis des Hauptrepositorys; sie werden nicht als
Wiki-Spiegel gepflegt. GitHub-Epics, Stories und Tasks dokumentieren die
veränderliche Umsetzung.

## Dokumentarten und Lebenszyklus

| Dokumentart | Primäre Zielgruppe und Zweck | Kanonische Quelle | Änderungsanlass |
| --- | --- | --- | --- |
| Einstieg | Personen, die eine passende Quelle für ihre Aufgabe finden müssen | `README.md`, `CONTRIBUTING.md` oder der jeweilige Abschnittsindex | Zielgruppe, Einstieg oder verlinkte kanonische Quelle ändert sich |
| Anleitung | Fachlichkeit, Nutzende oder Betreiber bei einem wiederkehrenden Arbeitsablauf | GitHub Wiki | Der aktuelle Arbeitsablauf oder seine Voraussetzungen ändern sich |
| Runbook | Maintainer bei einem heute ausführbaren betrieblichen Vorgang | Wenige aktuelle Seiten im Hauptrepository | Automation, Voraussetzungen, sichere Befehle, erwartetes Ergebnis oder Rückfallgrenze ändern sich |
| Referenz | Entwickelnde und Prüfer bei einem aktuellen Vertrag oder einer Schnittstelle | Ausführbarer Code, deklarative Modelle, Schema, Migrationen, Workflows oder daraus generierte Referenzen | Der zugrunde liegende Vertrag ändert sich; Prosa ergänzt nur nicht offensichtliche Semantik |
| ADR | Entscheidende und Entwickelnde bei einer langfristigen technischen Weichenstellung | `docs/developers/decisions/` und sein Index | Eine neue oder ablösende Entscheidung wird akzeptiert |

Ein Einstieg verweist knapp, statt Inhalte aller Ziele zu wiederholen.
Anleitungen und Runbooks enthalten nur aktuell gültige Abläufe. Ein Runbook
beschreibt Voraussetzungen, sichere Befehle, erwartete Ergebnisse,
Fehlerdiagnose und Rückfallgrenzen, aber weder Projektplanung noch historische
Evidenz. Referenzen werden nicht als manuelle zweite Gesamtauflistung neben
ihrer ausführbaren Quelle gepflegt.

Ungültige historische Dokumente werden gelöscht; Git, Tags, GitHub Releases
und gegebenenfalls ADR-Ersetzungsverweise bleiben die historische Quelle. Es
entsteht kein Archivverzeichnis und keine dauerhafte dateibezogene
Bestandsliste. Gekürzte, ausführliche oder als Arbeitskopie bezeichnete
Parallelfassungen werden nicht angelegt.

## Kanonische Ablage

- Redaktionelle Anleitungen für Menschen zu Einrichtung, Arbeitsprozess und
  Qualität liegen im GitHub Wiki.
- Architekturentscheidungen liegen als ADRs im Hauptrepository.
- API-Verträge liegen in OpenAPI beziehungsweise den deklarativen HTTP-Modellen;
  Datenmodell und Datenbankschema liegen in ORM, Schema, Migrationen und daraus
  generierten Referenzen.
- Qualitäts- und Releaseautomation liegt in Workflows und Taskfile;
  Veröffentlichungshistorie in Git-Tags, GitHub Releases und Changelog.
- Generierte Python- und TypeScript-Referenzen entstehen aus dem Code und sind
  CI-Artefakte; sie werden nicht als redaktionelle Kopie gepflegt.
- Agentenspezifische Regeln liegen in `AGENTS.md` oder in dafür vorgesehenen
  Codex-Artefakten, nicht in einer allgemeinen Entwickleranleitung.

## ADR-Konvention

Ein ADR ist erforderlich, wenn eine langfristige technische Entscheidung mit
relevanten Alternativen mehrere Komponenten, Teams oder spätere Änderungen
bindet. Lokale Implementierungsdetails, erledigte Umsetzungsschritte, reine
Konfiguration ohne Wahlmöglichkeit und Projektplanung erhalten keinen ADR.

Dauerhafte technische Entscheidungen stehen unter
`docs/developers/decisions/`; der Dateiname hat das Muster
`NNNN-kebab-case.md`. Neue ADRs verwenden die
[Vorlage](decisions/TEMPLATE.md) mit Status, ursprünglichem
Entscheidungsdatum, Kontext, Entscheidung, Konsequenzen, Alternativen und
Referenzen.

Ein akzeptierter ADR wird nicht inhaltlich umgeschrieben. Löst ein neuer ADR
seine fortgeltende Entscheidung vollständig ab, nennt der neue ADR im Abschnitt
`Status` `Supersedes: ADR-NNNN`; der abgelöste ADR erhält im selben Abschnitt
die einzige zulässige Ergänzung `Superseded by: ADR-NNNN`. Ergänzt oder
präzisiert ein ADR nur einen Teilbereich, bleibt der ältere ADR gültig und die
Beziehung wird in Kontext oder Referenzen erklärt, nicht als Ablösung markiert.
Der [Entscheidungsindex](decisions/index.md) führt den jeweiligen Status; er
ist keine Projekt- oder Migrationsplanung.

Die Zielarchitektur für den späteren gemeinsamen Produkt-, Wiki- und
Referenzauftritt steht unter
[Öffentliche Publikationsarchitektur](publication-architecture.md). Der lokale
Build unter `task docs:publication` erzeugt das vollständige statische
Artefakt; `task docs:publication:check` prüft die Reproduzierbarkeit und
`task docs:publication:browser` sowie `task docs:publication:a11y` prüfen den
sichtbaren Einstieg getrennt mit Playwright und axe. Der Workflow
`Public site` führt diese Prüfungen repositoryseitig aus. Pull Requests und
Pushes laden nur ein Workflow-Artefakt hoch. Eine Veröffentlichung ist davon
getrennt und ausschließlich nach dem dokumentierten manuellen Maintainer-Gate
möglich.

Öffentliche Python-Module, Services, Repositories, fachliche Klassen und nicht offensichtliche Funktionen verwenden Google-Style-Docstrings. Beschreiben Sie Invarianten, sichtbare Seiteneffekte, Fehler und Transaktionsgrenzen, ohne triviale Implementierungsdetails oder Typen zu wiederholen.

Exportierte TypeScript-Services, Modelle und fachliche Komponenten oder Methoden verwenden TSDoc. Kommentare erklären Semantik, Zustandsübergänge, Ownership und Seiteneffekte; HTTP-Verträge bleiben in OpenAPI.

MkDocs und `mkdocstrings` erzeugen die technische Dokumentation und Python-Referenz. TypeDoc erzeugt mit dem gelockten TypeScript-Compiler die Frontend-Referenz. `task docs` baut beide; CI veröffentlicht `site/` als geschütztes Artefakt `lzug-documentation`. TypeDoc wurde Compodoc vorgezogen, weil Compodoc einen abweichenden eingebetteten TypeScript-Compiler verwendet hätte. Das öffentliche redaktionelle Handbuch liegt ausschließlich im separaten GitHub Wiki und wird nicht in `site/` oder im Hauptrepository gespiegelt.

Bei Änderungen öffentlicher Schnittstellen aktualisieren Sie die passende Dokumentation, wenn ihre Bedeutung nicht offensichtlich ist. Die vollständige Dokumentation ist kein pauschales Nachdokumentieren von Legacy-Code.
