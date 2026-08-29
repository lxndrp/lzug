# ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`

## Datum

2026-08-08.

## Status

Akzeptiert.

## Kontext

Die bestehende Architektur besteht aus Angular-Frontend, Python-Backend, REST-API und SQLite.
Die erste Veröffentlichung soll für einen einzelnen Ausschuss mit Docker oder Podman und ohne separaten Datenbankdienst self-hostbar sein.
Dafür braucht die Runtime eine eindeutige Grenze zwischen flüchtigem Container-Dateisystem und dauerhaftem Anwendungszustand.

## Entscheidung

Das kanonische Auslieferungsformat ist ein OCI-Image.
Die Referenzruntime liefert gebrauchsfertiges Angular-Frontend, Python-Backend und REST-API in einem einzelnen Anwendungscontainer aus.
Self-Hosting verwendet SQLite.

Der dauerhafte Anwendungszustand liegt ausschließlich unter dem einen persistent eingebundenen Verzeichnis `/data` mit der folgenden Zielstruktur:

```text
/data/
├── lzug.sqlite
├── documents/
└── backups/
```

Damit sind `/data/lzug.sqlite`, `/data/documents/` und `/data/backups/` die verbindlichen Pfadgrenzen für Datenbank, Dokumente und Sicherungen.
Die konkrete SQLite-Verbindungs-, Journal-, Sperr- und Migrationskonfiguration bleibt den nachgelagerten Issues #116 und #117 überlassen.
Ein späterer Dokumentenspeicher kann über die in #118 vorgesehene Abstraktion ergänzt werden; ein S3-kompatibler Dienst gehört nicht zur ersten Veröffentlichung.

## Konsequenzen

- Das Image kann unter Docker und Podman als eine Anwendung gestartet werden;
ein separater Datenbankcontainer ist für die Referenzinstallation nicht erforderlich.
- Ein Container-Neustart oder ein neues Image darf den Inhalt von `/data`
nicht ersetzen.
- #116 muss SQLite auf den vereinbarten Pfad unter `/data` beziehen und darf
keinen fest codierten Repository-Pfad voraussetzen.
- #118 muss Datenbank, Dokumente und Sicherungen unter `/data` halten und
Zugriffe auf Dokumente über einen kontrollierten Speicheradapter führen.
- Details wie Prozessbenutzer, Root-Dateisystem, Healthcheck und
Build-Stufen gehören zur OCI-Umsetzung in #115; sie werden durch diesen ADR nicht vorweggenommen.

## Alternativen

- Frontend, Backend und Datenbank in mehrere Pflichtcontainer aufteilen:
würde die erste Referenzinstallation ohne nachgewiesenen Nutzen komplizierter machen.
- Einen externen Datenbankdienst als Voraussetzung festlegen: würde das
dezentrale Self-Hosting und die lokale Betriebsfähigkeit einschränken.
- Schreibbare Daten an beliebigen Containerpfaden ablegen: würde Updates und
Neustarts datenverlustgefährdet machen.

## Referenzen

- [Architekturübersicht](../architecture/index.md)
- [Backend und Datenzugriff](../architecture/backend.md)
- [Datenbankschema](../database-schema.md)
- [ADR-0001: Lokale relationale Persistenz](0001-lokale-relationale-persistenz.md)
- [ADR-0013: Dezentrale Instanzen je Ausschuss](0013-dezentrale-instanzen-je-ausschuss.md)
- Issues [#116](https://github.com/lxndrp/lzug/issues/116), [#117](https://github.com/lxndrp/lzug/issues/117) und [#118](https://github.com/lxndrp/lzug/issues/118)
