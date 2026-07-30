# Wiki-Publikation

Das GitHub Wiki ist ein separates Git-Repository. Es ist die einzige Quelle
für die öffentlichen Handbuchseiten; das Hauptrepository enthält keine
gespiegelten Wiki-Dateien. Das Hauptrepository enthält nur die Prüfprogramme,
Workflows und diese Verfahrensbeschreibung.

## Review- und Veröffentlichungsablauf

1. Ein Maintainer initialisiert das Wiki über GitHub, falls das Wiki noch nicht
   aktiviert ist, und stellt den Default-Branch fest.
2. Die redaktionelle Arbeit erfolgt in einem lokalen Clone von
   `https://github.com/lxndrp/lzug.wiki.git` auf einem separaten
   Review-Branch. Der Inhalt umfasst mindestens `Home.md` und `_Sidebar.md`
   sowie die vier Zielgruppenbereiche Fachlichkeit, Nutzung, Administration und
   Entwicklung.
3. Vor einer Veröffentlichung wird der konkrete Wiki-Branch oder Commit über
   `Actions -> Wiki pre-publish check` als `wiki_ref` geprüft. Der Check läuft
   gegen genau diesen Inhalt, nicht gegen eine Kopie im Hauptrepository.
4. Ein Maintainer prüft den Diff und die Prüfergebnisse. Erst diese explizite
   Entscheidung ist die Freigabe für die öffentliche Mutation.
5. Der Maintainer veröffentlicht exakt den geprüften Commit in den
   Default-Branch des Wiki-Repositories. Es gibt keinen automatischen Push aus
   dem Hauptrepository und keinen Force-Push.
6. Das `gollum`-Event startet danach den
   [Post-Publish-Check](https://github.com/lxndrp/lzug/blob/master/.github/workflows/wiki-post-publish.yml).
   Er checkt den Default-Branch erneut, prüft portable Links und öffentliche
   Sicherheitsregeln und lädt jede Seite mit Gollum.

Der aktuell veröffentlichte Wiki-Stand ist historisch und wird durch die
Korrektur dieses Issues ersetzt. Der neue Kandidat wird nach dem lokalen
Nachweis als konkreter Commit im separaten Wiki-Repository referenziert. Der
lokal geprüfte Kandidat dieses Umsetzungsthreads ist derzeit
`f8478d75c4195d74ca28d8fc3e67a052ff04b4e1` auf dem Branch
`codex/205-wiki-ssot-korrektur`; er ist noch nicht in den öffentlichen
Wiki-Clone gepusht. Bis zur expliziten Maintainer-Entscheidung bleibt der
Wiki-Default-Branch unverändert; das Hauptrepository nimmt keine öffentliche
Mutation vor.

## Inhaltliche Grenzen

Das Wiki beschreibt nur den vorhandenen Produkt- und Betriebsstand. ADRs,
OpenAPI-Vertrag, Datenbankschema, Migrationen, technische Modelle,
Docstrings/TSDoc und CI-/Security-/Deployment-Konfiguration bleiben im
Hauptrepository. Generierte Referenzen bleiben CI-Artefakte. Produktive
Self-Hosting-, Backup- und Upgrade-Anleitungen gehören zu #130; Pages und eine
Landingpage gehören zu #206.

## Lokale Prüfung eines Wiki-Clones

Mit einem ausgecheckten Wiki-Repository kann der portable Teil lokal geprüft
werden:

```sh
WIKI_ROOT=/path/to/lzug.wiki task wiki:check
```

Der Gollum-Lauf ist bewusst auf den isolierten, digest-gepinnten Container im
GitHub-Workflow begrenzt. So wird die bestehende Python/npm-Toolchain des
Projekts nicht um eine Ruby-Abhängigkeit erweitert. Der Post-Publish-Workflow
prüft zusätzlich jede flache Wiki-Seite über ihre gerenderte GitHub-Route auf
HTTP 200 und `Content-Type: text/html`; Weiterleitungen auf
`raw.githubusercontent.com` sind Fehler.
