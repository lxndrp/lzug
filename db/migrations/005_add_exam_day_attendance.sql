BEGIN;

ALTER TABLE exam_slot ADD COLUMN actual_started_at TEXT;

CREATE TABLE candidate_exam_attendance (
  id INTEGER PRIMARY KEY,
  exam_slot_id INTEGER NOT NULL REFERENCES exam_slot(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'present', 'late', 'absent')),
  arrived_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_slot_id),
  CHECK (
    status = 'present'
    OR (status = 'late' AND arrived_at IS NOT NULL)
    OR (status IN ('open', 'absent') AND arrived_at IS NULL)
  )
);

CREATE TABLE member_exam_attendance (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'present', 'late', 'absent')),
  arrived_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_day_id, committee_member_id),
  CHECK (
    status = 'present'
    OR (status = 'late' AND arrived_at IS NOT NULL)
    OR (status IN ('open', 'absent') AND arrived_at IS NULL)
  )
);

CREATE INDEX member_exam_attendance_day_status
  ON member_exam_attendance(exam_day_id, status);

INSERT INTO schema_migration (name) VALUES ('005_add_exam_day_attendance.sql');
COMMIT;
