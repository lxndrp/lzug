# ADR-0001: Lokale relationale Persistenz

## Datum

2026-07-26.

## Status

Akzeptiert.
Rückwirkend dokumentiert.

## Kontext

Die Anwendung benötigt ein ausführbares, lokal testbares Datenmodell.

## Entscheidung

SQLite ist die lokale Entwicklungsdatenbank.
`db/schema.sql` und die versionierten Migrationen sind die einzige getrackte
SQL-Quelle.
`fixtures/synthetic-fixtures.json` und `fixtures/generate.py` kompilieren bei
Bedarf disposable Entwicklungs- und Public-Demo-Seeds in ein Build- oder
Testverzeichnis.
Versionierte Änderungen liegen unter `db/migrations/` und werden in
`schema_migration` festgehalten.

Primärschlüssel sind zunächst `INTEGER PRIMARY KEY`, Enums `TEXT` mit `CHECK`, Zeitstempel `TEXT` und Booleans `INTEGER` mit Check-Constraint.
Mehrzeilige Fachregeln validiert die Anwendung.

## Konsequenzen

Die Entwicklung bleibt ohne separaten Datenbankdienst möglich.
Ein späterer PostgreSQL-Wechsel bleibt vorbereitet, verlangt aber eine bewusste Migration von IDs, Zeitstempeln, Booleans, Enums und gegebenenfalls zusätzlichen Constraints.
Die aktuelle technische Referenz ist `db/schema.sql`.
