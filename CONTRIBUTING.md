# Zu lzug beitragen

Danke für Beiträge zu `lzug`. Dieses Dokument beschreibt die verbindlichen
Beitragsregeln. Einrichtung, tägliche Entwicklung und die Auswahl passender
lokaler Prüfungen stehen im Bereich
[Entwicklung](https://github.com/lxndrp/lzug/wiki/Entwicklung) des GitHub Wiki.
Fachliche Prioritäten und Akzeptanzkriterien bleiben in den
[GitHub Issues](https://github.com/lxndrp/lzug/issues); die Maintainer pflegen
die operative Reihenfolge zusätzlich im GitHub Project `lzug Roadmap`.

`lzug` ist ein ausdrücklich nicht produktionsreifer Quellcode-Prototyp mit synthetischen Demo- und Testdaten.
Das Projekt ist nicht offiziell mit der IHK verbunden.
Beiträge dürfen daher keine Produktionsreife, IHK-Zugehörigkeit oder produktive Betriebszusage voraussetzen.

## Einstieg

Folgen Sie vor der ersten Änderung dem
[Entwickler-Setup](https://github.com/lxndrp/lzug/wiki/Entwicklung-Einrichtung).
Der [Arbeitsprozess](https://github.com/lxndrp/lzug/wiki/Entwicklung-Arbeitsprozess)
beschreibt Issue-Planung, Branches, Verifikation und Abschluss; die
[Qualitätssicherung](https://github.com/lxndrp/lzug/wiki/Entwicklung-Qualitaet-und-Sicherheit)
legt die risikobasierte Auswahl lokaler Prüfungen fest. Architektur, API-Vertrag
und technische Dokumentationsstandards stehen im
[Entwicklerhandbuch](docs/developers/index.md).

Das [GitHub Wiki](https://github.com/lxndrp/lzug/wiki) enthält die
redaktionellen Entwicklungsanleitungen. Die Zuordnung aller Dokumentarten und
kanonischen Quellen steht unter
[Entwicklung](docs/developers/development.md#dokumentation-bearbeiten); der
konkrete Wiki-Review- und Veröffentlichungsablauf unter
[Delivery und Veröffentlichung](docs/developers/delivery.md#wiki-publikation).

Eigene gepflegte Markdown-Prosa wird mit Semantic Line Breaks geschrieben: Sätze und sinnvolle Gedankeneinheiten beginnen in neuen Quellzeilen.
Tabellen, Listenstruktur, Codeblöcke, Front Matter, URLs und technische Zeichenketten bleiben unverändert; Drittmaterial, Lizenztexte und generierte Inhalte werden nicht rein redaktionell umgebrochen.

## Änderungen einreichen

- Änderungen gehören zu einem GitHub Issue und bleiben klein sowie thematisch
zusammenhängend.
- Commits werden auf Englisch geschrieben.
- Prüfe Project, Milestone und Assignees des Issues mit `gh issue view` und
öffne den Pull Request mit `task pr:create`.
Übergib gesetzte Assignees und den Milestone explizit; die Task ordnet den PR dem Project `lzug Roadmap` zu.
- Ein vollständiger Pull Request enthält `Closes #<nummer>`, eine
Teilumsetzung eine nicht schließende Verknüpfung.
- Prüfe die Zuordnungen nach dem Erstellen mit `gh pr view`.
- CI und Review sind Voraussetzung für den Merge.

Die vollständigen Befehle und der Ablauf bis zum Closeout stehen unter
[Pull Request und Closeout](docs/developers/development.md#pull-request-und-closeout).

Release-Tags und öffentliche Artefakte bleiben Maintainer-Aufgaben.
Der verbindliche SemVer-, Changelog-, GitHub-Release- und GHCR-Ablauf steht
unter [Release und Artefakte](docs/developers/delivery.md#release-und-artefakte);
ein Pull Request oder Merge allein löst keine Veröffentlichung aus.
