# Datenbankschema

Die aktuelle, ausführbare Schema-Referenz ist `db/schema.sql` im Repository. Sie und die versionierten Migrationen unter `db/migrations/` sind maßgeblich für den tatsächlichen Datenbankstand.

Das aktuelle Backend verwendet SQLite lokal und SQLAlchemy. Primärschlüssel,
Enums, Zeitstempel und Booleans sind SQLite-kompatibel modelliert; mehrzeilige
fachliche Regeln werden in Repositories und Services validiert. Die Entscheidung einschließlich des später möglichen PostgreSQL-Pfads hält [ADR-0001](decisions/0001-lokale-relationale-persistenz.md) fest.

Diese Referenz ersetzt weder `db/schema.sql` noch die Migrationen.
