# Reproduzierbare öffentliche Site

Der Build setzt den in ADR-0023 beschlossenen statischen Artefaktschnitt um. Er
veröffentlicht selbst nichts und verwendet lokal standardmäßig nur die minimale
synthetische Wiki-Fixture in diesem Verzeichnis.

```sh
task docs:publication
task docs:publication:check
task docs:publication:browser
task docs:publication:a11y
```

Mit einem sauberen lokalen Clone des echten Wiki-Repositories kann derselbe
Buildschnitt geprüft werden:

```sh
task docs:publication WIKI_ROOT=/path/to/lzug.wiki
```

`BASE_URL` ist dauerhaft `https://lzug.repertoire.papaspyrou.name` an der
Domainwurzel. `DEMO_URL` bindet eine separat konfigurierbare Demo-Origin an das
Artefakt und darf keine Credentials, Query, Fragment oder Unterpfade enthalten.
Die Demo-Domain bleibt bis zur Maintainer-Bestätigung offen; der Azure-
Standard-FQDN ist kein Produktvertrag. Der Build pinnt Hugo Extended und den exakt visuell geprüften
Relearn-Commit.
Relearn benötigt weder npm noch Go Modules und übernimmt keine zweite
Lockdatei in dieses Repository. Die Ausgabe unter
`build/publication/` enthält die beschlossene URL-Struktur, einen lokalen
Suchindex und `quellen.json` mit Hauptrepository-, Wiki- und Theme-Revision.
`docs:publication:check` baut zweimal und vergleicht alle Ausgabedateien
bytegenau. Das kleine repository-eigene Root-Layout enthält den Produkt- und
Demo-Einstieg. Der Warm-up ruft ausschließlich `/api/ready` ohne Cookies oder
Referrer auf, wartet höchstens 90 Sekunden in zwölf begrenzten Versuchen und
leitet erst bei `status=ready` weiter. Danach bietet dieselbe primäre Aktion einen
neuen Versuch an.

Die früheren Spike-Tasknamen wurden ohne Kompatibilitätsalias entfernt. Alle
Aufrufer verwenden die oben gezeigten produktiven Befehle.

Der Workflow `Public site` baut bei Pull Requests und Pushes auf `master` nur
ein geprüftes Artefakt. Der vorbereitete Pages-Job ist ausschließlich manuell
auf `master` mit ausdrücklichem Bestätigungsinput erreichbar und aktiviert
Pages nicht selbst. Pages-Konfiguration und erster Dispatch benötigen ein
separates Maintainer-GO; ohne dieses GO findet keine Veröffentlichung statt.

Der Browser-Task startet ausschließlich einen kurzlebigen lokalen Server,
prüft Root-Seite und Handbuch mit Chromium auf Desktop und Mobil, verwirft
kritische beziehungsweise schwerwiegende axe-Befunde und beendet Browser und
Server auch im Fehlerfall. Screenshots landen nur im ignorierten `build/`.
