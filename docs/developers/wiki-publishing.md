# Wiki-Publikation

Das GitHub Wiki ist ein separates Git-Repository. Es ist die einzige Quelle
für die öffentlichen Handbuchseiten; das Hauptrepository enthält keine
gespiegelten Wiki-Dateien. Das Hauptrepository enthält nur die Prüfprogramme,
den einzelnen Post-Publish-Workflow und diese Verfahrensbeschreibung.

## Review- und Veröffentlichungsablauf

1. Ein Maintainer initialisiert das Wiki über GitHub, falls das Wiki noch nicht
   aktiviert ist, und stellt den Default-Branch fest.
2. Die redaktionelle Arbeit erfolgt in einem lokalen Clone von
   `https://github.com/lxndrp/lzug.wiki.git` auf einem separaten
   Review-Branch. Der Inhalt umfasst mindestens `Home.md` und `_Sidebar.md`
   sowie die vier Zielgruppenbereiche Fachlichkeit, Nutzung, Administration und
   Entwicklung.
3. `_Sidebar.md` ist die vollständige kanonische Liste der öffentlichen
   Inhaltsseiten. Vor einer Veröffentlichung prüft der Maintainer den konkret
   ausgecheckten Stand lokal mit
   `WIKI_ROOT=/path/to/lzug.wiki task wiki:check`.
4. Ein Maintainer prüft den Diff und die Prüfergebnisse. Erst diese explizite
   Entscheidung ist die Freigabe für die öffentliche Mutation.
5. Der Maintainer veröffentlicht exakt den geprüften Commit in den
   Default-Branch des Wiki-Repositories. Es gibt keinen automatischen Push aus
   dem Hauptrepository und keinen Force-Push.
6. Der Maintainer kann danach den rein diagnostischen
   [Post-Publish-Check](https://github.com/lxndrp/lzug/blob/master/.github/workflows/wiki-post-publish.yml)
   manuell starten. Derselbe Check läuft wöchentlich, leitet aus der Sidebar
   die erwarteten gerenderten Wiki-Routen ab und prüft sie mit Lychee ohne
   Weiterleitungen. Er ist kein Produktrelease- oder Demo-Deployment-Gate.

Das Wiki-Repository ist initialisiert. Der veröffentlichte Stand wird dort
versioniert und ist die kanonische Quelle für das redaktionelle Handbuch. Die
Dokumentation einer Wiki-Commit-ID in einem GitHub-Issue ist keine generelle
Prozesspflicht; dieses Repository enthält bewusst keine Kopie der Wiki-Seiten.

## Inhaltliche Grenzen

Das Wiki beschreibt nur den vorhandenen Produkt- und Betriebsstand. ADRs,
OpenAPI-Vertrag, Datenbankschema, Migrationen, technische Modelle,
Docstrings/TSDoc und CI-/Security-/Deployment-Konfiguration bleiben im
Hauptrepository. Generierte Referenzen bleiben CI-Artefakte. Produktive
Self-Hosting-, Backup- und Upgrade-Anleitungen werden erst mit den jeweiligen
ausführbaren Betriebsverfahren ergänzt.

## Lokale Prüfung eines Wiki-Clones

Mit einem ausgecheckten Wiki-Repository kann der portable Teil lokal geprüft
werden:

```sh
WIKI_ROOT=/path/to/lzug.wiki task wiki:check
```

Der kleine Python-Validator prüft nur die lzug-spezifische Invariante, dass die
flachen Inhaltsseiten und die kanonische `_Sidebar.md` vollständig
übereinstimmen. Lychee `v0.24.2` übernimmt die generische Markdown- und
Quelllinkprüfung. Nach Veröffentlichung erzeugt der rein lesende
periodische beziehungsweise manuell gestartete Workflow aus der Sidebar eine
temporäre Markdown-Liste und prüft nur die erwarteten GitHub-Routen mit
höchstens null Weiterleitungen; so sind Weiterleitungen auf Rohdaten oder
andere Ziele Fehler. Die Liste wird nicht als CI-Artefakt hochgeladen. Weder
der lokale Task noch der Workflow pushen in das Wiki oder benötigen ein
zusätzliches Schreib-Token. Die langfristige Publikationsarchitektur bleibt
Gegenstand von #206.
