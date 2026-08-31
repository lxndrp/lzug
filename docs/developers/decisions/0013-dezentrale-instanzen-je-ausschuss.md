# ADR-0013: Dezentrale Instanzen je Ausschuss

## Datum

2026-08-08.

## Status

Akzeptiert.

## Kontext

`lzug` unterstützt die Arbeit von Prüfungsausschüssen.
Für die erste Veröffentlichung soll ein Ausschuss die Anwendung selbst betreiben können und dabei eine eigene Konfiguration, eigene Nutzer, eigene Fachdaten, eigene Sicherungen und eine eigene URL erhalten.
Eine zentrale Plattform mit mehreren fachlich voneinander getrennten Ausschüssen wäre dagegen eine Mandantenarchitektur und würde zusätzliche Isolations-, Berechtigungs- und Betriebsentscheidungen voraussetzen.

## Entscheidung

Die fachliche und betriebliche Grenze eines Ausschusses ist die Self-Hosting-Instanz.
Innerhalb einer Instanz gibt es keine fachliche Mandantenfähigkeit für mehrere voneinander isolierte Ausschüsse.
Ausschüsse, die getrennte Daten- und Betreibergrenzen benötigen, betreiben getrennte Instanzen.

Diese Entscheidung beschreibt die Instanzgrenze, nicht die fachlichen Rollen und Berechtigungen innerhalb eines Ausschusses.
Sie führt auch keine zentrale Benutzerverwaltung oder einen besonderen Identitätsdienst ein.

## Konsequenzen

- Die Auslieferung und die Referenzinstallation können auf einen einzelnen
Ausschuss und dessen Datenbestand ausgerichtet werden.
- Datenisolation entsteht durch getrennte Instanzen und nicht durch einen
zusätzlichen Mandantenschlüssel in jeder fachlichen Tabelle.
- Betreiber müssen Instanzen, Konfiguration, Sicherungen und URLs je Ausschuss
getrennt verwalten.
- Eine spätere zentral betriebene Mandantenflotte benötigt weiterhin getrennte
Laufzeit- und Datenhaltungsgrenzen; sie wird in [ADR-0016](0016-spaetere-mandantenflotte.md) als späteres Zielbild beschrieben.

## Alternativen

- Mehrere Ausschüsse in einer Self-Hosting-Instanz mandantenfähig trennen:
würde zusätzliche fachliche und sicherheitsrelevante Grenzen in Anwendung, Datenmodell und Betrieb erfordern und ist für die erste Veröffentlichung nicht notwendig.
- Einen zentralen Dienst als einziges Betriebsmodell vorgeben: würde das
dezentrale Self-Hosting-Ziel aufgeben.

## Referenzen

- [Architekturübersicht](../architecture.md)
- [ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`](0014-oci-einzelcontainer-und-persistentes-data.md)
- Epic [#113](https://github.com/lxndrp/lzug/issues/113)
- Umsetzung [#114](https://github.com/lxndrp/lzug/issues/114)
