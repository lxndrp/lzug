# lzug

[![License: GPL-2.0](https://img.shields.io/badge/license-GPL--2.0-blue.svg)](LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-yellow)](https://github.com/lxndrp/lzug/issues)
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
operative Maintainer-Roadmap wird separat im GitHub Project gepflegt.

## Dokumentation

Das versionierte Handbuch richtet sich an drei Zielgruppen:

- [Nutzungsanleitung](docs/users/index.md): vorhandene Abläufe in der Anwendung.
- [Lokale Administration](docs/administrators/index.md): Entwicklungsinstanz
  einrichten, starten und zurücksetzen.
- [Entwicklerhandbuch](docs/developers/index.md): Architektur, Referenzen,
  Entscheidungen und Qualitätssicherung.

Für Beiträge und lokale Entwicklung ist [CONTRIBUTING.md](CONTRIBUTING.md) der
Einstieg. Die lokale Dokumentation inklusive Code-Referenzen entsteht mit:

```sh
task docs
```

Das Ergebnis liegt unter `site/` und wird in CI als geschütztes Artefakt
`lzug-documentation` bereitgestellt.

## Lizenz

Dieses Projekt steht unter der [GPL-2.0-Lizenz](LICENSE).

## Abgrenzung

Dieses Repository veröffentlicht den Quellcode eines fachlichen Prototyps.
Ein produktives Release mit belastbarer Authentifizierung, Rollenrechten,
Datenschutz-, Betriebs-, Backup-, Upgrade- oder Supportzusage ist nicht Teil
dieser Veröffentlichung. Diese Themen werden getrennt im
[Release- und Betriebs-Epic #113](https://github.com/lxndrp/lzug/issues/113)
geplant.
