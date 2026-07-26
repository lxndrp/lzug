# lzug

[![License: GPL-2.0](https://img.shields.io/badge/license-GPL--2.0-blue.svg)](LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-yellow)](https://github.com/users/lxndrp/projects/2)
[![CI](https://github.com/lxndrp/lzug/actions/workflows/ci.yml/badge.svg?branch=master&event=push)](https://github.com/lxndrp/lzug/actions/workflows/ci.yml?query=branch%3Amaster+event%3Apush)

`lzug` unterstützt IHK-Prüfungsausschüsse bei der Organisation halbjährlicher
Fachinformatiker-Prüfungen. Die Anwendung ist ein Arbeitswerkzeug für die
Ausschussarbeit, nicht für die interne IHK-Sachbearbeitung.

Der aktuelle Prototyp unterstützt die Pflege von Prüfungshalbjahren,
Ausschüssen, Prüflingen und Prüfungsorten sowie die Planung von möglichen
Prüfungstagen, Verfügbarkeiten und Prüfungsvorschlägen. Der genaue Arbeitsstand
steht im GitHub Project [lzug Roadmap](https://github.com/users/lxndrp/projects/2)
und in den zugehörigen Issues.

## Dokumentation

Das versionierte Handbuch richtet sich an drei Zielgruppen:

- [Nutzungsanleitung](docs/users/index.md): vorhandene Abläufe in der Anwendung.
- [Lokale Administration](docs/administrators/index.md): Entwicklungsinstanz
  einrichten, starten und zurücksetzen.
- [Entwicklerhandbuch](docs/developers/index.md): Architektur, Referenzen,
  Entscheidungen und Qualitätssicherung.

Für Beiträge und lokale Entwicklung ist [CONTRIBUTING.md](CONTRIBUTING.md) der
Einstieg. Die lokalen Dokumentation inklusive Code-Referenzen entsteht mit:

```sh
mise run docs
```

Das Ergebnis liegt unter `site/` und wird in CI als geschütztes Artefakt
`lzug-documentation` bereitgestellt.

## Lizenz

Dieses Projekt steht unter der [GPL-2.0-Lizenz](LICENSE).
