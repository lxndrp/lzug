BEGIN;

ALTER TABLE exam_slot ADD COLUMN execution_status TEXT NOT NULL DEFAULT 'open' CHECK (
  execution_status IN ('open', 'running', 'completed', 'cancelled', 'needs_follow_up')
);
ALTER TABLE exam_slot ADD COLUMN status_changed_at TEXT;
ALTER TABLE exam_slot ADD COLUMN actual_completed_at TEXT;
ALTER TABLE exam_slot ADD COLUMN status_reason TEXT;

UPDATE exam_slot
SET execution_status = CASE
      WHEN actual_started_at IS NOT NULL THEN 'running'
      ELSE 'open'
    END,
    status_changed_at = COALESCE(actual_started_at, CURRENT_TIMESTAMP);

INSERT INTO schema_migration (name) VALUES ('006_add_exam_execution_status.sql');
COMMIT;
