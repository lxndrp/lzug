# Reproduzierbarer Publikations-Spike

Der Spike belegt lokal den in ADR-0023 beschlossenen statischen Artefaktschnitt.
Er veröffentlicht nichts und verwendet standardmäßig nur die minimale
synthetische Wiki-Fixture in diesem Verzeichnis.

```sh
task docs:publication-spike
task docs:publication-spike:check
task docs:publication-spike:browser
```

Mit einem sauberen lokalen Clone des echten Wiki-Repositories kann derselbe
Buildschnitt geprüft werden:

```sh
task docs:publication-spike WIKI_ROOT=/path/to/lzug.wiki
```

Der Build pinnt Hugo Extended und den exakt visuell geprüften Relearn-Commit.
Relearn benötigt weder npm noch Go Modules und übernimmt keine zweite
Lockdatei in dieses Repository. Die Ausgabe unter
`build/publication-spike/` enthält die beschlossene URL-Struktur, einen lokalen
Suchindex und `quellen.json` mit Hauptrepository-, Wiki- und Theme-Revision.
`docs:publication-spike:check` baut zweimal und vergleicht alle Ausgabedateien
bytegenau. Das kleine repository-eigene Root-Layout belegt nur den attraktiven
Produkt-/Dokumentationsschnitt; Inhalt und endgültige Gestaltung aus #127
nimmt es nicht vorweg.

Der Browser-Task startet ausschließlich einen kurzlebigen lokalen Server,
prüft Root-Seite und Handbuch mit Chromium auf Desktop und Mobil, verwirft
kritische beziehungsweise schwerwiegende axe-Befunde und beendet Browser und
Server auch im Fehlerfall. Screenshots landen nur im ignorierten `build/`.
