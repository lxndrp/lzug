# Dokumentation und Architekturentscheidungen

Produkt-, Fach- und Architekturdokumentation ist auf Deutsch; Code-Kommentare sind Englisch. Planung, Prioritäten und Liefertermine gehören in GitHub Issues und das Roadmap-Project, nicht in ADRs.

Das öffentliche redaktionelle Handbuch liegt ausschließlich im [GitHub Wiki](https://github.com/lxndrp/lzug/wiki). Die Dateien unter `docs/` sind die technische und fachliche Quellbasis des Hauptrepositorys; sie werden nicht als Wiki-Spiegel gepflegt.

Die vollständige fachliche Handbuchquelle liegt im [GitHub Wiki](https://github.com/lxndrp/lzug/wiki). Dieses technische Handbuch beschreibt nur die code- und CI-gebundenen Quellen. GitHub-Epics, Stories und Tasks dokumentieren die veränderliche Umsetzung. Technisches Datenmodell, API-Vertrag und Architektur verbleiben im Entwicklerhandbuch.

## ADR-Konvention

Dauerhafte technische Entscheidungen stehen als ADR unter `docs/developers/decisions/`. Der Dateiname hat das Muster `NNNN-kebab-case.md`. Jeder ADR enthält Status, ursprüngliches Entscheidungsdatum, Kontext, Entscheidung, Konsequenzen, Alternativen und Referenzen. Ein akzeptierter ADR wird nicht inhaltlich umgeschrieben; eine spätere Änderung erhält einen neuen ADR, der den vorherigen ablöst oder ergänzt.

Öffentliche Python-Module, Services, Repositories, fachliche Klassen und nicht offensichtliche Funktionen verwenden Google-Style-Docstrings. Beschreiben Sie Invarianten, sichtbare Seiteneffekte, Fehler und Transaktionsgrenzen, ohne triviale Implementierungsdetails oder Typen zu wiederholen.

Exportierte TypeScript-Services, Modelle und fachliche Komponenten oder Methoden verwenden TSDoc. Kommentare erklären Semantik, Zustandsübergänge, Ownership und Seiteneffekte; HTTP-Verträge bleiben in OpenAPI.

MkDocs und `mkdocstrings` erzeugen die technische Dokumentation und Python-Referenz. TypeDoc erzeugt mit dem gelockten TypeScript-Compiler die Frontend-Referenz. `task docs` baut beide; CI veröffentlicht `site/` als geschütztes Artefakt `lzug-documentation`. TypeDoc wurde Compodoc vorgezogen, weil Compodoc einen abweichenden eingebetteten TypeScript-Compiler verwendet hätte. Das öffentliche redaktionelle Handbuch liegt ausschließlich im separaten GitHub Wiki und wird nicht in `site/` oder im Hauptrepository gespiegelt.

Bei Änderungen öffentlicher Schnittstellen aktualisieren Sie die passende Dokumentation, wenn ihre Bedeutung nicht offensichtlich ist. Die vollständige Dokumentation ist kein pauschales Nachdokumentieren von Legacy-Code.
