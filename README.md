# lzug

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-yellow)](https://github.com/users/lxndrp/projects/2)
[![CI](https://github.com/lxndrp/lzug/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/lxndrp/lzug/actions/workflows/ci.yml?query=branch%3Amaster+event%3Apush)

`lzug` unterstützt IHK-Prüfungsausschüsse bei der Organisation halbjährlicher
Fachinformatiker-Prüfungen. Die Anwendung ist ein Arbeitswerkzeug für die
Ausschussarbeit, nicht für die interne IHK-Sachbearbeitung.

> **Öffentlicher Quellcode-Prototyp:** Für die geplante Veröffentlichung gilt:
> Der Quellcode ist ausdrücklich nicht produktionsreif. Er enthält ausschließlich
> synthetische Demo- und Testdaten, keine produktive Authentifizierung und keine
> Zusage für Self-Hosting oder Betrieb. `lzug` steht in keiner offiziellen
> Beziehung zur IHK.

Der aktuelle Prototyp unterstützt die Pflege von Prüfungshalbjahren,
Ausschüssen, Prüflingen und Prüfungsorten sowie die Planung von möglichen
Prüfungstagen, Verfügbarkeiten und Prüfungsvorschlägen. Der genaue Arbeitsstand
steht in den [GitHub Issues](https://github.com/lxndrp/lzug/issues). Die
operative Maintainer-Roadmap wird separat im nicht-öffentlichen GitHub Project gepflegt.

## Dokumentation

Das öffentliche redaktionelle Handbuch richtet sich an Fachlichkeit, Nutzer,
Administratoren und Entwickler und liegt im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki). Das Wiki-Repository ist
separat; seine Seiten werden nicht im Hauptrepository gespiegelt.

Die technische Dokumentation im Hauptrepository umfasst:

- [Technische Dokumentation](docs/index.md): Architektur, Verträge,
  Datenmodell, Entscheidungen und Qualitätssicherung.
- [Entwicklerhandbuch](docs/developers/index.md): Architektur, Referenzen,
  Entscheidungen und Qualitätssicherung.

Die vollständige Fachlichkeit sowie das Nutzer- und Administratorhandbuch
liegen ausschließlich im [GitHub Wiki](https://github.com/lxndrp/lzug/wiki).

Für Beiträge und lokale Entwicklung ist [CONTRIBUTING.md](CONTRIBUTING.md) der
Einstieg. Die lokale Dokumentation inklusive Code-Referenzen entsteht mit:

```sh
task docs
```

Das Ergebnis liegt unter `site/` und wird in CI als geschütztes Artefakt
`lzug-documentation` bereitgestellt.

Der kontrollierte Wiki-Review- und Veröffentlichungsablauf steht unter
[Wiki-Publikation](docs/developers/wiki-publishing.md).

## Lizenz

Dieses Projekt steht unter der [GNU Affero General Public License
3.0-or-later](LICENSE). Änderungen an einer netzwerkbasiert betriebenen
Version müssen den interagierenden Nutzenden den entsprechenden Quellcode
zugänglich machen.
