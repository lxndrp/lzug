# lzug

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](LICENSE)
[![Status: prototype](https://img.shields.io/badge/status-prototype-yellow)](https://github.com/users/lxndrp/projects/2)
[![Quality](https://github.com/lxndrp/lzug/actions/workflows/quality.yml/badge.svg?branch=master&event=push)](https://github.com/lxndrp/lzug/actions/workflows/quality.yml?query=branch%3Amaster+event%3Apush)
[![Latest release](https://img.shields.io/github/v/release/lxndrp/lzug?display_name=tag)](https://github.com/lxndrp/lzug/releases)
[![Public site](https://github.com/lxndrp/lzug/actions/workflows/publication.yml/badge.svg?branch=master)](https://github.com/lxndrp/lzug/actions/workflows/publication.yml?query=branch%3Amaster)

`lzug` unterstützt IHK-Prüfungsausschüsse bei der Organisation halbjährlicher Fachinformatiker-Prüfungen.
Die Anwendung ist ein Arbeitswerkzeug für die Ausschussarbeit, nicht für die interne IHK-Sachbearbeitung.

Die [öffentliche Demo](https://demo.lzug.repertoire.papaspyrou.name) zeigt den aktuellen Prototyp.

> **Öffentlicher Quellcode-Prototyp:** `lzug` ist ausdrücklich nicht
> produktionsreif. Fachliche Demo-Daten sind synthetisch; bezeichnete Athener
> Anschriften und Referenzkoordinaten stammen aus den im Ortsdetail genannten
> Quellen. Beim Öffnen einer Karte lädt der Browser Inhalte von OpenStreetMap.
> Personenbezogene und fachliche Demo- und Testdaten sind ausschließlich
> synthetisch. Die lokale Kennwort-/TOTP-Authentifizierung ist kein Versprechen
> für produktiven Betrieb, Self-Hosting oder Support. `lzug` steht in keiner
> offiziellen Beziehung zur IHK.

Der genaue Arbeitsstand steht in den
[GitHub Issues](https://github.com/lxndrp/lzug/issues), veröffentlichte
Versionen in den [GitHub Releases](https://github.com/lxndrp/lzug/releases)
und die automatisierten Nachweise unter
[Actions](https://github.com/lxndrp/lzug/actions). Die Maintainer pflegen die
operative Reihenfolge im GitHub Project `lzug Roadmap`.

## Dokumentation

Wähle den Einstieg nach Aufgabe:

- Das öffentliche [Produkt- und Dokumentationsportal](https://lzug.repertoire.papaspyrou.name)
führt zu Produktinformation und Demo sowie zu Nutzer-, Betreiber- und Entwicklerdokumentation.
- Die [Betreiberanleitung](docs/portal/betreiben.md) führt durch Installation,
Bootstrap, Diagnose und das erste verifizierte Backup.
- Das [Nutzerhandbuch](docs/handbook/Nutzung.md) erklärt die fachliche Arbeit nach Anmeldung.
- [CONTRIBUTING.md](CONTRIBUTING.md) ist der Einstieg für Beiträge und lokale
Entwicklung.
- Das [Entwicklerhandbuch](docs/developers/index.md) enthält aktuelle
technische Verträge, Runbooks, Referenzen und Entscheidungen.

Das Repository ist die einzige kanonische Quelle.
Pages rendert diese Inhalte aus derselben Revision;
jede Seite verlinkt ihre Quelle und Build-Revision.
Der ehemalige Wiki-Bestand ist mit prüfbarem [Migrationsnachweis](docs/migrations/wiki-2026-09-03.md)
in das Repository übernommen.
`task docs` baut die versionierte technische Referenz lokal; CI stellt sie als geschütztes Artefakt bereit.

## Lizenz

Der Projektcode und ausführbare Beispiele stehen unter der [GNU Affero General Public License 3.0-or-later](LICENSE).
Änderungen an einer netzwerkbasiert betriebenen Version müssen den interagierenden Nutzenden den entsprechenden Quellcode zugänglich machen.
Originale Dokumentationsprosa und -diagramme stehen innerhalb der in [`docs/LICENSE.md`](docs/LICENSE.md) festgelegten Grenze unter `CC-BY-4.0`.
Drittmaterial behält die in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) dokumentierte Lizenz.
