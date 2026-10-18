-- Add immutable absence follow-up sources and an explicit legacy cutover.
BEGIN TRANSACTION;

ALTER TABLE exam_day_assignment ADD COLUMN revision INTEGER NOT NULL DEFAULT 1
  CHECK (revision >= 1);

CREATE TABLE absence_consequence_cutover (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  audit_watermark INTEGER NOT NULL CHECK (audit_watermark >= 0),
  captured_at TEXT NOT NULL
);

INSERT INTO absence_consequence_cutover (id, audit_watermark, captured_at)
SELECT 1, COALESCE(MAX(id), 0), CURRENT_TIMESTAMP FROM absence_audit_event;

CREATE TABLE absence_consequence_source (
  id INTEGER PRIMARY KEY,
  origin_id TEXT NOT NULL UNIQUE,
  audit_event_id INTEGER NOT NULL UNIQUE
    REFERENCES absence_audit_event(id) ON DELETE RESTRICT,
  absence_report_id INTEGER NOT NULL REFERENCES absence_report(id) ON DELETE RESTRICT,
  report_version INTEGER NOT NULL CHECK (report_version >= 0),
  assignment_id INTEGER NOT NULL REFERENCES exam_day_assignment(id) ON DELETE RESTRICT,
  assignment_revision INTEGER NOT NULL CHECK (assignment_revision >= 1),
  source_json TEXT NOT NULL CHECK (json_valid(source_json)),
  created_at TEXT NOT NULL
);

CREATE TRIGGER absence_consequence_source_no_update
BEFORE UPDATE ON absence_consequence_source
BEGIN
  SELECT RAISE(ABORT, 'absence consequence sources are immutable');
END;

CREATE TRIGGER absence_consequence_source_no_delete
BEFORE DELETE ON absence_consequence_source
BEGIN
  SELECT RAISE(ABORT, 'absence consequence sources are immutable');
END;

CREATE INDEX absence_consequence_source_report
  ON absence_consequence_source(absence_report_id, report_version);

CREATE TABLE calendar_assignment_execution_origin (
  assignment_id INTEGER PRIMARY KEY
    REFERENCES exam_day_assignment(id) ON DELETE CASCADE,
  origin_id TEXT NOT NULL,
  execution_version INTEGER NOT NULL CHECK (execution_version >= 1),
  updated_at TEXT NOT NULL,
  UNIQUE (assignment_id, execution_version)
);

INSERT INTO schema_migration (name)
VALUES ('029_add_absence_consequence_sources.sql');

COMMIT;
