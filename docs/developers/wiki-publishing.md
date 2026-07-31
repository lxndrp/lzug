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
3. `_Sidebar.md` ist die vollständige kanonische Liste der öffentlichen
   Inhaltsseiten. Vor einer Veröffentlichung wird der konkrete Wiki-Branch oder
   Commit über `Actions -> Wiki pre-publish check` als `wiki_ref` geprüft. Der
   Check läuft gegen genau diesen Inhalt, nicht gegen eine Kopie im
   Hauptrepository.
4. Ein Maintainer prüft den Diff und die Prüfergebnisse. Erst diese explizite
   Entscheidung ist die Freigabe für die öffentliche Mutation.
5. Der Maintainer veröffentlicht exakt den geprüften Commit in den
   Default-Branch des Wiki-Repositories. Es gibt keinen automatischen Push aus
   dem Hauptrepository und keinen Force-Push.
6. Das `gollum`-Event startet danach den
   [Post-Publish-Check](https://github.com/lxndrp/lzug/blob/master/.github/workflows/wiki-post-publish.yml).
   Er prüft den Default-Branch erneut, erzeugt aus der Sidebar eine temporäre
   Sitemap und lässt Lychee sowohl die Quelllinks als auch die erwarteten
   gerenderten Wiki-Routen prüfen.

Das Wiki-Repository ist initialisiert. Der veröffentlichte Stand wird dort
versioniert und ist die kanonische Quelle für das redaktionelle Handbuch. Die
jeweils geprüfte Wiki-Commit-ID wird im zugehörigen GitHub-Issue dokumentiert;
dieses Repository enthält bewusst keine Kopie der Wiki-Seiten.

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

Der Task erzeugt die Sitemap nur in einem temporären Verzeichnis. Sie ist kein
versioniertes Wiki-Artefakt und keine zweite Seitenliste. Der Python-Validator
prüft die bidirektionale Sidebar-Synchronität, Routenform und öffentliche
Sicherheitsregeln; Lychee `v0.24.2` prüft die Quelllinks. Nach Veröffentlichung
prüft Lychee die aus der Sitemap abgeleiteten GitHub-Routen mit höchstens null
Weiterleitungen; so sind Weiterleitungen auf Rohdaten oder andere Ziele Fehler.
Der Workflow lädt die erzeugte Sitemap bei Bedarf als Diagnoseartefakt hoch.
