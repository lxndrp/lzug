# ADR-0039: Deklarative Toolchain-Zuständigkeiten

## Datum

2026-09-25.

## Status

Akzeptiert.

## Kontext

Die bisherigen Toolchain- und Adapterentscheidungen ordnen einzelne Werkzeuge
und Abläufe zu.
Eine gemeinsame Regel muss zusätzlich festlegen, welche Ebene gemeinsame
Policy, dynamische Aufrufdaten, Komponentenverhalten und nötige
Querschnittslogik besitzt.
Die frühere pauschale Forderung, Repository-Tooling nach PowerShell zu
migrieren und Python auszuschließen, bildet diese Grenzen nicht ab.

## Entscheidung

Die Entscheidungsreihenfolge lautet:

1. Gemeinsame stabile Werkzeug-Policy liegt einmalig in der nativen,
   deklarativen Konfiguration des Werkzeugs.
2. Standardwerkzeuge bauen, prüfen, generieren und paketieren direkt anhand
   ihrer nativen Konfiguration und Standardmechanismen.
3. Verbleibende Logik wird nach Verantwortung, Sprache und Ablageort
   zugeordnet.

`mise` stellt Versionen ausführbarer Werkzeuge und die Entwicklungsumgebung
bereit.
Paketmanager besitzen Paketabhängigkeiten und deren native Manifest- und
Lockdateien.
`Task` ist der einzige öffentliche komponentenübergreifende Ablaufgraph;
das Root-Taskfile aggregiert und Komponenten-Taskfiles besitzen ihre lokalen
Abläufe.
GitHub Actions besitzt Auslöser, Runner, Berechtigungen, Artefakttransport und
Freigaben.
Projektarbeit verwendet dieselben Task- und Werkzeugverträge wie lokal.

Rein komponentenbezogene Logik liegt in der Sprache und Codebase der
zuständigen Komponente.
Ein nativer Komponentenexport darf das vorhandene Fach- oder Artefaktmodell
wiederverwenden; der OpenAPI-Export des Backends ist ein Beispiel.
Die Sprache eines konsumierten Werkzeugs oder Artefakts bestimmt nicht die
Verantwortung.
Komponentenübergreifendes Skripting, das sich nicht durch deklarative
Konfiguration, Task oder Standardwerkzeuge abbilden lässt, wird grundsätzlich
in PowerShell umgesetzt und möglichst nahe am verantwortlichen
Querschnittsaspekt abgelegt.
Allgemeines Repository-Skripting liegt ebenfalls in PowerShell unter
`scripts/`.
Direkte Standardwerkzeug-Aufrufe in Task sind keine zusätzliche
Skriptschicht.

Stabile gemeinsame Policy und dynamische Aufrufdaten bleiben getrennt.
Die scannerweite Policy in `.syft.yaml` ist stabil und deklarativ; Scan-Ziel,
Ausgabe und laufbezogene Parameter bleiben am jeweiligen Aufruf sichtbar.
Eine universelle Projektkonfigurationssprache oder ein Generator für sämtliche
Werkzeugkonfigurationen wird nicht eingeführt.

Die pauschale Python-Ausschlussvorgabe aus #810 gilt nicht mehr.
Eine notwendige Überführung nach PowerShell ist Teil der Zuständigkeitsregel,
belegt für sich allein aber keine Vereinfachung.
Bloßes Verschieben, Umschreiben oder Zusammenkopieren generischer
Orchestrierung in ein Komponentenmodul erfüllt das Vereinfachungsziel nicht.
Zusätzliche Prüfungen benötigen einen realistischen Fehlerfall, einen
betroffenen Verbraucher und die kleinste ausreichende Prüfebene;
unabhängige Risikogrenzen bleiben eigenständig.

## Konsequenzen

Native Konfiguration und Standardmechanismen werden vor eigener Skriptlogik
geprüft.
Jede verbleibende Logik hat einen nachvollziehbaren Eigentümer und Ablageort;
Aufrufe halten die konkreten Ziele und laufbezogenen Eingaben sichtbar.
Das Werkzeuginventar beschreibt den aktuellen Tree und begründet verbleibende
Eigenlogik, ohne geplante Folgearbeiten als umgesetzt auszugeben.

## Referenzen

- [ADR-0003: Toolchain mit mise, uv und npm](0003-toolchain-mise-uv-npm.md)
- [ADR-0009: Toolchain und Entwicklungs-Tasks trennen](0009-toolchain-und-entwicklungs-tasks.md)
- [ADR-0021: GoReleaser für die Betreiber-CLI](0021-goreleaser-fuer-die-betreiber-cli.md)
- [ADR-0036: PowerShell-Adapter für portable Werkzeuggrenzen](0036-powershell-adapter-fuer-werkzeuggrenzen.md)
- [ADR-0037: PowerShell/Pester-Testharness](0037-powershell-pester-testharness.md)
- [ADR-0038: SBOM-Erzeugung als direkte Syft-Standardaufrufe](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md)
- [Entwicklung](../development.md)
- [Werkzeuginventar](../script-inventory.md)
