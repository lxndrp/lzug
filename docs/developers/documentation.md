# Dokumentation und Architekturentscheidungen

Produkt-, Fach- und Architekturdokumentation ist auf Deutsch; Code-Kommentare sind Englisch. Planung, Prioritäten und Liefertermine gehören in GitHub Issues und das Roadmap-Project, nicht in ADRs.

Das öffentliche redaktionelle Handbuch liegt ausschließlich im [GitHub Wiki](https://github.com/lxndrp/lzug/wiki). Die Dateien unter `docs/` sind die technische Quellbasis des Hauptrepositorys; sie werden nicht als Wiki-Spiegel gepflegt.

Die vollständige fachliche Handbuchquelle liegt im [GitHub Wiki](https://github.com/lxndrp/lzug/wiki). Dieses technische Handbuch beschreibt nur die code-, CI-, Security-, Release- und entscheidungsgebundenen Quellen. GitHub-Epics, Stories und Tasks dokumentieren die veränderliche Umsetzung.

## Kanonische Ablage

Jeder Inhalt besitzt genau eine kanonische Ablage:

- Redaktionelle Anleitungen für Menschen zu Einrichtung, Arbeitsprozess und
  Qualität liegen im GitHub Wiki.
- Technische Architektur, Datenmodell, API-Vertrag, Datenbankschema, ADRs,
  Frontend-Richtlinien, Reviews, Fixtures, Lizenz- und Release-Nachweise sowie
  Wiki-Publikationsprüfungen liegen im Hauptrepository.
- Generierte Python- und TypeScript-Referenzen entstehen aus dem Code und sind
  CI-Artefakte; sie werden nicht als redaktionelle Kopie gepflegt.
- Agentenspezifische Regeln liegen in `AGENTS.md` oder in dafür vorgesehenen
  Codex-Artefakten, nicht in einer allgemeinen Entwickleranleitung.

Gekürzte, ausführliche oder als Arbeitskopie bezeichnete Parallelfassungen
werden nicht angelegt. Die fachliche Handbuchquelle liegt ebenfalls im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki); technische Modelle und
Verträge verbleiben im Entwicklerhandbuch.

## ADR-Konvention

Dauerhafte technische Entscheidungen stehen als ADR unter `docs/developers/decisions/`. Der Dateiname hat das Muster `NNNN-kebab-case.md`. Jeder ADR enthält Status, ursprüngliches Entscheidungsdatum, Kontext, Entscheidung, Konsequenzen, Alternativen und Referenzen. Ein akzeptierter ADR wird nicht inhaltlich umgeschrieben; eine spätere Änderung erhält einen neuen ADR, der den vorherigen ablöst oder ergänzt.

Öffentliche Python-Module, Services, Repositories, fachliche Klassen und nicht offensichtliche Funktionen verwenden Google-Style-Docstrings. Beschreiben Sie Invarianten, sichtbare Seiteneffekte, Fehler und Transaktionsgrenzen, ohne triviale Implementierungsdetails oder Typen zu wiederholen.

Exportierte TypeScript-Services, Modelle und fachliche Komponenten oder Methoden verwenden TSDoc. Kommentare erklären Semantik, Zustandsübergänge, Ownership und Seiteneffekte; HTTP-Verträge bleiben in OpenAPI.

MkDocs und `mkdocstrings` erzeugen die technische Dokumentation und Python-Referenz. TypeDoc erzeugt mit dem gelockten TypeScript-Compiler die Frontend-Referenz. `task docs` baut beide; CI veröffentlicht `site/` als geschütztes Artefakt `lzug-documentation`. TypeDoc wurde Compodoc vorgezogen, weil Compodoc einen abweichenden eingebetteten TypeScript-Compiler verwendet hätte. Das öffentliche redaktionelle Handbuch liegt ausschließlich im separaten GitHub Wiki und wird nicht in `site/` oder im Hauptrepository gespiegelt.

Bei Änderungen öffentlicher Schnittstellen aktualisieren Sie die passende Dokumentation, wenn ihre Bedeutung nicht offensichtlich ist. Die vollständige Dokumentation ist kein pauschales Nachdokumentieren von Legacy-Code.
