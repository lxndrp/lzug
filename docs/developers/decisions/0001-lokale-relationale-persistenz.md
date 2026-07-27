# ADR-0001: Lokale relationale Persistenz

## Status

Akzeptiert, rückwirkend dokumentiert am 26.07.2026.

## Kontext und Entscheidung

Die Anwendung benötigt ein ausführbares, lokal testbares Datenmodell. SQLite ist die lokale Entwicklungsdatenbank. `db/schema.sql` und `db/seed_demo.sql` bleiben die ausführbaren Quellen; versionierte Änderungen liegen unter `db/migrations/` und werden in `schema_migration` festgehalten.

Primärschlüssel sind zunächst `INTEGER PRIMARY KEY`, Enums `TEXT` mit `CHECK`, Zeitstempel `TEXT` und Booleans `INTEGER` mit Check-Constraint. Mehrzeilige Fachregeln validiert die Anwendung.

## Konsequenzen

Die Entwicklung bleibt ohne separaten Datenbankdienst möglich. Ein späterer PostgreSQL-Wechsel bleibt vorbereitet, verlangt aber eine bewusste Migration von IDs, Zeitstempeln, Booleans, Enums und gegebenenfalls zusätzlichen Constraints. Die aktuelle technische Referenz ist `db/schema.sql`.
