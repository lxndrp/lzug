-- Keep migration file checksums separate so old schema_migration tables remain
-- upgradeable without a non-transactional SQLite column rewrite.
BEGIN;

CREATE TABLE IF NOT EXISTS schema_migration_checksum (
  name TEXT PRIMARY KEY REFERENCES schema_migration(name) ON DELETE CASCADE,
  checksum TEXT NOT NULL CHECK (length(checksum) = 64)
);

INSERT INTO schema_migration (name) VALUES ('009_harden_migration_history.sql');
COMMIT;
