# ADR-0023: Öffentliche Web- und Dokumentationspublikation

## Status

Akzeptiert am 14.08.2026.

## Kontext

lzug benötigt einen attraktiven öffentlichen Produkt- und Demo-Einstieg, ein
aus dem GitHub Wiki projiziertes Handbuch sowie generierte technische
Referenzen. Hauptrepository und Wiki sind unabhängige Git-Repositories. Eine
öffentliche Ausgabe darf deshalb keine neue redaktionelle Quelle werden und
muss beide Revisionen nachweisen.

Diese Entscheidung ergänzt ADR-0007 für die öffentliche
Publikationsarchitektur. MkDocs und TypeDoc bleiben interne beziehungsweise
spezialisierte Referenzgeneratoren.

Plattform, Generator und Theme wurden getrennt anhand derselben Kriterien
verglichen: Produktauftritt, Navigation, Suche, Barrierefreiheit, Responsive
Design, Wartungsaufwand, Toolchain-Last, Quellenkennzeichnung,
Single-Source-of-Truth und reproduzierbarer Betrieb. Doks und Relearn wurden
zusätzlich mit identischem Inhalt auf Desktop und Mobil gebaut und geprüft;
Docsy wurde als konzeptionelle Referenz eingeordnet.

## Entscheidung

1. Zielplattform ist **GitHub Pages mit einem eigenen GitHub-Actions-Build**.
   #206 aktiviert weder Pages noch ein Deployment-Environment.
2. **Hugo Extended** baut die öffentliche Hülle. **Hugo Relearn** ist das
   gewählte Theme für Handbuch, Navigation und lokale Suche.
3. Ein kleines repository-eigenes Root-Layout ergänzt den attraktiven
   Produkteinstieg. Es bleibt bewusst unabhängig von einer weiteren
   JavaScript-, npm- oder Go-Module-Toolchain.
4. **Doks** bleibt visuelle Gestaltungsreferenz, wird wegen seines gemessenen
   npm-, Update- und Security-Aufwands nicht übernommen. **Docsy** wird
   ebenfalls nicht übernommen.
5. MkDocs/mkdocstrings, TypeDoc, OpenAPI/Redoc und die Schemaansicht bleiben
   unabhängige, task-basierte Generatoren. Hugo montiert ihre statischen
   Ausgaben; kein Generator schreibt in die Quelle eines anderen.
6. Das Wiki bleibt kanonische Quelle für redaktionelles Handbuchmaterial.
   Technische Dokumentation, Docstrings, TSDoc, OpenAPI und Datenbankschema
   bleiben im Hauptrepository kanonisch. Die Pages-Ausgabe ist nur Projektion.
7. Jede Ausgabe enthält Repository-, Wiki- und Theme-Revision sichtbar unter
   `/quellen/` sowie maschinenlesbar in `/quellen.json`.

Die kanonischen Routen sind `/`, `/handbuch/`, `/referenz/backend/`,
`/referenz/frontend/`, `/referenz/api/`, `/referenz/datenbank/` und
`/quellen/`. Ein Deployment ersetzt immer genau ein vollständig geprüftes
Artefakt.

## Konsequenzen

- Hugo Extended kommt als gepinnte Toolchain-Komponente hinzu; MkDocs wird
  nicht entfernt.
- Relearn liefert eine schlanke Dokumentationsbasis. Das kleine Root-Layout
  erhöht den repository-eigenen Gestaltungsanteil; Semantik,
  Tastaturbedienung, Kontrast, Suche und Responsive-Verhalten bleiben
  projektspezifische Aktivierungsgates.
- Pull Requests bauen und prüfen ohne Deployment. `push` auf `master`,
  `gollum` und explizite `workflow_dispatch`-Refs können später ein atomar
  deploybares Artefakt erzeugen. Build und Deployment bleiben getrennt.
- Wiki-Inhalte werden aus einem beim Build aufgelösten Commit temporär
  projiziert. Weder Wiki-Kopie noch generierte HTML-Ausgaben werden als Quelle
  eingecheckt.
- Der lokale Spike pinnt den geprüften Relearn-Commit, benötigt keine
  zusätzliche Paketmanager-Lockdatei und veröffentlicht nichts.

## Migration

1. #206 liefert nur Entscheidung, Dokumentation und lokalen Spike.
2. #127 gestaltet den Produkt- und Demo-Einstieg innerhalb der hier
   festgelegten Hülle, ohne die Quellenzuständigkeiten zu verändern.
3. Ein eigener Umsetzungsschritt führt Security- und Accessibility-Prüfungen
   ein, gestaltet das Root-Layout produktiv und baut die unabhängigen
   Referenz-Tasks aus.
4. Erst nach Maintainer-Freigabe werden Pages, Berechtigungen, geschütztes
   Environment und Deployment-Workflow aktiviert.

## Rückfallpfad

Scheitert Relearn an einer später belegten funktionalen Anforderung, bleibt der
Hugo-Inhalts- und Routenschnitt stabil und das Theme kann getrennt ersetzt
werden. Scheitert GitHub Pages an einer belegten notwendigen Plattformfunktion,
kann dasselbe statische
Artefakt auf Netlify betrieben werden. Read the Docs bleibt nur für eine
später bewusst getrennte, versionierte Dokumentationssite geeignet. Ein
Rückfall auf das interne MkDocs-Artefakt ist möglich, erfüllt aber nicht den
beschlossenen öffentlichen Produktauftritt.

## Verworfene Alternativen

- **MkDocs-Basistheme als öffentliche Hülle:** zu schwache visuelle Grundlage
  für den gemeinsamen Produkt- und Dokumentationsauftritt.
- **Doks:** beste fertige Produktwirkung im visuellen Vergleich, aber 394 npm-
  Abhängigkeiten und 95 aktuelle transitive Audit-Befunde im geprüften
  Produktionsbaum widersprechen dem Einfachheitsprinzip.
- **Docsy:** größter Toolchain- und Komponentenaufwand ohne entsprechenden
  Nutzen für den aktuellen Umfang.
- **Netlify als Erstplattform:** zusätzliche externe Betriebs- und
  Berechtigungsoberfläche ohne derzeit notwendige Plattformfunktion.
- **Read the Docs als Erstplattform:** passt schlechter zum gemeinsamen
  Produkt-, Wiki- und Referenzartefakt aus zwei Git-Quellen.

## Referenzen

- [ADR-0007: MkDocs und Code-Referenzen](0007-dokumentation-und-code-referenz.md)
- [ADR-0012: Wiki Single Source of Truth](0012-wiki-single-source-of-truth.md)
- [GitHub Pages mit eigenen Workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [Doks](https://getdoks.org/)
- [Hugo Relearn](https://mcshelby.github.io/hugo-theme-relearn/)
- [Docsy](https://www.docsy.dev/)
