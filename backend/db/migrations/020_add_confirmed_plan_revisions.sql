-- Preserve every controlled change to a confirmed plan as an immutable revision.
BEGIN TRANSACTION;

CREATE TABLE confirmed_plan_revision (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  previous_revision INTEGER NOT NULL CHECK (previous_revision >= 0),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision > previous_revision),
  reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  before_state_json TEXT NOT NULL,
  after_state_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, resulting_revision)
);

CREATE INDEX confirmed_plan_revision_history
  ON confirmed_plan_revision(exam_round_id, resulting_revision);

INSERT INTO schema_migration (name) VALUES ('020_add_confirmed_plan_revisions.sql');
COMMIT;
