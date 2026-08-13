# Zu lzug beitragen

Danke für Beiträge zu `lzug`. Dieses Dokument beschreibt die verbindlichen
Beitragsregeln. Einrichtung, tägliche Entwicklung und die Auswahl passender
lokaler Prüfungen stehen im Bereich
[Entwicklung](https://github.com/lxndrp/lzug/wiki/Entwicklung) des GitHub Wiki.
Fachliche Prioritäten und Akzeptanzkriterien bleiben in den
[GitHub Issues](https://github.com/lxndrp/lzug/issues); die Maintainer pflegen
die operative Reihenfolge zusätzlich im GitHub Project `lzug Roadmap`.

`lzug` ist ein ausdrücklich nicht produktionsreifer Quellcode-Prototyp mit
synthetischen Demo- und Testdaten. Das Projekt ist nicht offiziell mit der IHK
verbunden. Beiträge dürfen daher keine Produktionsreife, IHK-Zugehörigkeit oder
produktive Betriebszusage voraussetzen.

## Einstieg

Folgen Sie vor der ersten Änderung dem
[Entwickler-Setup](https://github.com/lxndrp/lzug/wiki/Entwicklung-Einrichtung).
Der [Arbeitsprozess](https://github.com/lxndrp/lzug/wiki/Entwicklung-Arbeitsprozess)
beschreibt Issue-Planung, Branches, Verifikation und Abschluss; die
[Qualitätssicherung](https://github.com/lxndrp/lzug/wiki/Entwicklung-Qualitaet-und-Sicherheit)
legt die risikobasierte Auswahl lokaler Prüfungen fest. Architektur, API-Vertrag
und technische Dokumentationsstandards stehen im
[Entwicklerhandbuch](docs/developers/index.md).

Das öffentliche redaktionelle Handbuch liegt ausschließlich im separaten
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki) und wird nicht in diesem
Repository gespiegelt. Wiki-Änderungen werden in einem separaten Clone mit dem
lokalen `task wiki:check` geprüft und erst nach Maintainer-Freigabe manuell in
den Default-Branch veröffentlicht.
Der genaue Ablauf steht in der [Wiki-Publikation](docs/developers/wiki-publishing.md).

## Änderungen einreichen

- Änderungen gehören zu einem GitHub Issue und bleiben klein sowie thematisch
  zusammenhängend.
- Commits werden auf Englisch geschrieben.
- Öffne den Pull Request mit `scripts/create-issue-pr.sh`; das Script übernimmt
  Project, Milestone und Assignees aus dem Issue.
- Ein vollständiger Pull Request enthält `Closes #<nummer>`, eine
  Teilumsetzung eine nicht schließende Verknüpfung.
- CI und Review sind Voraussetzung für den Merge.

Release-Tags und öffentliche Artefakte bleiben Maintainer-Aufgaben. Der
verbindliche SemVer-, Changelog-, GitHub-Release- und GHCR-Ablauf steht im
[Release-Prozess](docs/developers/releases.md); ein Pull Request oder Merge
allein löst keine Veröffentlichung aus.
