BEGIN;

ALTER TABLE exam_slot ADD COLUMN execution_status TEXT NOT NULL DEFAULT 'open' CHECK (
  execution_status IN ('open', 'running', 'completed', 'cancelled', 'needs_follow_up')
);
-- SQLite cannot use CURRENT_TIMESTAMP as the default of an added column.
-- The empty default is replaced by the insert trigger below, while keeping
-- the column non-nullable for migrated databases.
ALTER TABLE exam_slot ADD COLUMN status_changed_at TEXT NOT NULL DEFAULT '';
ALTER TABLE exam_slot ADD COLUMN actual_completed_at TEXT;
ALTER TABLE exam_slot ADD COLUMN status_reason TEXT;

UPDATE exam_slot
SET execution_status = CASE
      WHEN actual_started_at IS NOT NULL THEN 'running'
      ELSE 'open'
    END,
    status_changed_at = COALESCE(actual_started_at, CURRENT_TIMESTAMP);

CREATE TRIGGER exam_slot_status_changed_at_on_insert
AFTER INSERT ON exam_slot
WHEN NEW.status_changed_at = ''
BEGIN
  UPDATE exam_slot
  SET status_changed_at = CURRENT_TIMESTAMP
  WHERE id = NEW.id;
END;

INSERT INTO schema_migration (name) VALUES ('006_add_exam_execution_status.sql');
COMMIT;
