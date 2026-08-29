# ADR-0016: Spätere getrennte Mandantenflotte

## Datum

2026-08-08.

## Status

Akzeptiert als Zielbild; nicht Bestandteil der ersten Veröffentlichung.

## Kontext

Nach der dezentralen Self-Hosting-Veröffentlichung kann ein zentral betriebener Dienst mit mehreren Ausschüssen sinnvoll werden.
Dieses Zielbild benötigt eine andere Betriebsform als eine einzelne lokale Instanz.
Die fachliche Isolation darf dabei nicht von einer gemeinsamen Anwendung oder gemeinsamen Datenbank abhängen.

## Entscheidung

Die spätere Mandantenflotte besteht aus getrennten Azure Container Apps je Mandant und getrennter externer Datenhaltung je Mandant.
Die Provisionierung und Änderung der Infrastruktur erfolgt deklarativ mit OpenTofu.
GitHub Actions authentifiziert sich für Azure über OIDC; langfristige Azure- Client-Secrets werden dafür nicht als Betriebsgrundlage eingeführt.

Die Flotte ist ein nachrangiges Ausbauziel.
Sie erweitert weder die erste Self-Hosting-Runtime noch die flüchtige Demo um fachliche Mandantenfähigkeit.
Identitäts-, Rollen-, Netzwerk-, Kosten-, Skalierungs- und konkrete DBaaS- Entscheidungen bleiben eigene Folgeentscheidungen.

## Konsequenzen

- Ein Mandant kann unabhängig deployt, skaliert, diagnostiziert und
zurückgesetzt werden.
- Datenhaltung und Lebenszyklus eines Mandanten bleiben von anderen
Mandanten getrennt.
- OpenTofu-Code und OIDC-Berechtigungen werden später als eigene
Betriebs- und Security-Arbeitspakete spezifiziert.
- Die erste Veröffentlichung braucht weder externe DBaaS noch OpenTofu oder
OIDC, um als dezentrale Self-Hosting-Anwendung zu funktionieren.
- Eine gemeinsame Mandantenplattform wäre eine neue Architekturentscheidung;
sie darf diese Trennungsentscheidung nicht stillschweigend ersetzen.

## Alternativen

- Alle Mandanten in einer gemeinsamen Container App und Datenbank betreiben:
würde die beschlossene Laufzeit- und Datenisolation schwächen.
- Die zentrale Mandantenflotte als Voraussetzung der ersten Veröffentlichung
umsetzen: würde den dezentralen Erstveröffentlichungspfad unnötig verzögern.
- Infrastruktur manuell statt deklarativ verwalten: würde Reproduzierbarkeit
und kontrollierte Änderungen verschlechtern.

## Referenzen

- [ADR-0013: Dezentrale Instanzen je Ausschuss](0013-dezentrale-instanzen-je-ausschuss.md)
- [ADR-0015: Flüchtige Azure-Container-Apps-Demo](0015-fluechtige-azure-demo.md)
- [Architekturübersicht](../architecture/index.md)
- Epic [#113](https://github.com/lxndrp/lzug/issues/113)
- Nachrangige Konzepte [#133](https://github.com/lxndrp/lzug/issues/133) und [#134](https://github.com/lxndrp/lzug/issues/134)
