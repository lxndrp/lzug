# ADR-0015: Flüchtige Azure-Container-Apps-Demo

## Status

Akzeptiert am 08.08.2026.

## Kontext

Die öffentliche Vorstellung von `lzug` benötigt eine erreichbare Demo. Diese
Demo dient der Anschauung und dem Smoke-Test der Auslieferung, nicht dem
Betrieb von Ausschussdaten. Eine dauerhaft gespeicherte Demo würde die
fachliche und datenschutzbezogene Grenze zum Self-Hosting verwischen und
zusätzliche Betriebsverantwortung erzeugen.

## Entscheidung

Die öffentliche Demo läuft flüchtig in Azure Container Apps. Sie verwendet
ausschließlich vorbereitete synthetische Demodaten und besitzt keine
verbindliche dauerhafte Datenhaltung. Eine statische Landingpage bildet den
öffentlichen Einstieg, erklärt den Demo-Charakter und führt kontrolliert zur
Demo-Instanz beziehungsweise unterstützt deren Warm-up.

Die Demo ist ein separates Veröffentlichungsziel. Sie ist weder die
Referenzinstallation für Self-Hosting noch eine Mandanteninstanz für reale
Ausschussdaten. Konkrete Azure-Ressourcen, Domains, TLS-, Reset- und
Beobachtbarkeitsdetails werden in den dafür vorgesehenen Folge-Issues
entschieden.

## Konsequenzen

- Demo-Daten dürfen bei Neustart, Skalierung oder Zurücksetzung verloren gehen.
- Landingpage und Demo müssen ihren flüchtigen Charakter klar kommunizieren.
- Ein Smoke-Test prüft die Erreichbarkeit jedes Demo-Deployments; sein
  konkreter Ablauf gehört zur späteren Demo-Umsetzung.
- Self-Hosting-Dokumentation darf die Azure-Demo nicht als Voraussetzung
  darstellen.
- Eine persistente Sicherung oder Migration von Demo-Daten ist nicht Teil
  dieses Betriebsmodells.

## Alternativen

- Eine dauerhaft betriebene Demo mit produktionsähnlicher Datenbank: würde
  dauerhafte Daten- und Betriebsverantwortung für einen Anschauungsdienst
  einführen.
- Die Demo im Self-Hosting-OCI-Referenzmodell betreiben: würde die
  öffentliche Demo mit dem Installations- und Persistenzpfad koppeln.
- Nur eine statische Seite ohne laufende Anwendung veröffentlichen: würde den
  Runtime- und Bediennachweis der Anwendung nicht erbringen.

## Referenzen

- [Architekturübersicht](../architecture/index.md)
- [ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`](0014-oci-einzelcontainer-und-persistentes-data.md)
- Epic [#113](https://github.com/lxndrp/lzug/issues/113)
- Folge-Issues [#124](https://github.com/lxndrp/lzug/issues/124) bis [#129](https://github.com/lxndrp/lzug/issues/129)
