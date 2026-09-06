-- Add the optimistic revision for atomically stored planning proposals.
BEGIN TRANSACTION;

ALTER TABLE exam_round
  ADD COLUMN plan_revision INTEGER NOT NULL DEFAULT 0
  CHECK (plan_revision >= 0);

INSERT INTO schema_migration (name) VALUES ('012_add_plan_revision.sql');
COMMIT;
