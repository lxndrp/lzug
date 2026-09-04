# ADR-0032: Repository-zentrierte öffentliche Dokumentation

## Datum

2026-09-03.

## Status

Akzeptiert am 2026-09-03.
Supersedes: ADR-0011.
Supersedes: ADR-0012.
Supersedes: ADR-0023.

## Kontext

Produktinformation, Handbuch, Betrieb und technische Referenzen benötigen einen gemeinsamen öffentlichen Einstieg.
Eine Wiki-Projektion erzeugt dafür zwei redaktionelle Git-Quellen und getrennte Revisionsnachweise.
Der öffentliche Auftritt muss die vollständige Dokumentation durchsuchen können,
die Build-Revision sichtbar machen und ohne Kopien oder eine zusätzliche Publishing-Toolchain auskommen.

## Entscheidung

1. Das Hauptrepository ist die einzige kanonische Quelle für Produkt-, Nutzer-, Betreiber- und Entwicklerdokumentation einschließlich Architektur und ADRs.
2. GitHub Pages rendert aus derselben Repository-Revision eine vollständige öffentliche Produkt- und Dokumentationssite.
3. Die vier Einstiege sind Produkt/Demo, Nutzung, Self-Hosting/Betrieb und Entwicklung.
   Inhalte dürfen daraus zielgruppengerecht mehrfach verlinkt werden,
   erhalten aber keine zweite redaktionelle Quelle.
4. Jede gerenderte Seite zeigt die Build-Revision und verlinkt ihre kanonische Markdown-Quelle im Repository.
5. Die redaktionellen Handbuchseiten liegen versioniert unter `docs/handbook/`.
   Struktur- und Navigationsprüfungen sichern den aktuellen Repository-Bestand.
6. Das GitHub Wiki ist keine Quelle für die öffentliche Dokumentation.
   Es entsteht weder ein dauerhafter Wiki-Checker noch ein Parallelarchiv.
7. Hugo/Relearn bleibt die schlanke Hülle für Navigation, Suche, Responsive-Verhalten und Corporate Design.
   MkDocs, TypeDoc und OpenAPI bleiben unabhängige Generatoren und werden nur in das Zielartefakt montiert.

## Konsequenzen

- Änderungen an CLI, Konfiguration, Rollen oder fachlichen Abläufen aktualisieren die betroffene kanonische Markdown-Seite im selben Auftrag.
- Der Public-Site-Workflow checkt keine Wiki-Repository-Revision mehr aus.
- Die öffentliche Produktseite bleibt kompakt und verweist unmittelbar auf die drei Dokumentationspfade.
- Die Versionierung der Page-Ausgabe ist an den gebauten Produkt-Commit gebunden;
  eine Freigabe der Demo-URL oder eines Deployments bleibt davon getrennt.

## Rückfallpfad

Fällt die Page-Auslieferung aus,
bleibt die Dokumentation direkt im Hauptrepository lesbar und mit dem lokalen `task docs` baubar.
Ein erneuter Wiki-Betrieb wäre eine neue, ausdrücklich entschiedene und migrationsfähige Publikationsarchitektur,
nicht ein impliziter Rückfall.

## Verworfene Alternativen

- **Weiteres kanonisches Wiki:** erzeugt weiterhin zwei Redaktions- und Revisionsquellen.
- **Eingecheckte HTML-Projektion:** dupliziert generierte Ausgabe und verschleiert die Quelle.
- **Separates Dokumentations-Repository:** erhöht Berechtigungs-, Release- und Synchronisationsaufwand ohne Produktnutzen.

## Referenzen

- [Publications-Skript](https://github.com/lxndrp/lzug/blob/master/docs/publication.py)
- [ADR-0007: MkDocs und Code-Referenzen](0007-dokumentation-und-code-referenz.md)
