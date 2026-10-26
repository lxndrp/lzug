-- Persist non-secret reservation and revocation generations for calendar feeds.
BEGIN TRANSACTION;

CREATE TABLE calendar_feed_lifecycle (
  person_id INTEGER PRIMARY KEY REFERENCES person(id) ON DELETE CASCADE,
  generation INTEGER NOT NULL DEFAULT 0 CHECK (generation >= 0),
  pending_generation INTEGER CHECK (pending_generation IS NULL OR pending_generation >= 1),
  revocation_generation INTEGER NOT NULL DEFAULT 0 CHECK (revocation_generation >= 0),
  revoked_at TEXT
);

INSERT INTO calendar_feed_lifecycle (
  person_id,
  generation,
  pending_generation,
  revocation_generation,
  revoked_at
)
SELECT
  person_id,
  CASE WHEN revoked_at IS NULL THEN 1 ELSE 0 END,
  NULL,
  CASE WHEN revoked_at IS NULL THEN 0 ELSE 1 END,
  revoked_at
FROM calendar_feed;

INSERT INTO schema_migration (name)
VALUES ('030_calendar_feed_lifecycle.sql');

COMMIT;
