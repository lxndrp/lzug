-- Move formal completion from the shared half-year to each committee-specific round.
BEGIN TRANSACTION;

ALTER TABLE exam_half_year ADD COLUMN legacy_status TEXT;

CREATE TABLE exam_half_year_migration_evidence (
  id INTEGER PRIMARY KEY,
  exam_half_year_id INTEGER NOT NULL REFERENCES exam_half_year(id) ON DELETE RESTRICT,
  previous_status TEXT NOT NULL,
  resulting_status TEXT NOT NULL,
  migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO exam_half_year_migration_evidence (
  exam_half_year_id, previous_status, resulting_status
)
SELECT id, status, 'archived'
FROM exam_half_year
WHERE status IN ('completed', 'archived');

UPDATE exam_half_year
SET legacy_status = status,
    status = 'archived',
    updated_at = CURRENT_TIMESTAMP
WHERE status IN ('completed', 'archived');

ALTER TABLE exam_round ADD COLUMN revision INTEGER NOT NULL DEFAULT 1
  CHECK (revision >= 1);
ALTER TABLE exam_round ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT 'open'
  CHECK (lifecycle_status IN ('open', 'closed', 'cancelled', 'reopening', 'historical'));
ALTER TABLE exam_round ADD COLUMN legacy_status TEXT;

UPDATE exam_round
SET lifecycle_status = CASE
      WHEN status = 'completed' THEN 'historical'
      WHEN status = 'cancelled' THEN 'cancelled'
      ELSE 'open'
    END,
    legacy_status = CASE
      WHEN status IN ('completed', 'cancelled') THEN status
      ELSE NULL
    END;

CREATE TABLE exam_round_migration_evidence (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE RESTRICT,
  previous_status TEXT NOT NULL,
  resulting_lifecycle_status TEXT NOT NULL,
  clarification_required INTEGER NOT NULL DEFAULT 0 CHECK (clarification_required IN (0, 1)),
  migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO exam_round_migration_evidence (
  exam_round_id, previous_status, resulting_lifecycle_status, clarification_required
)
SELECT
  id,
  status,
  lifecycle_status,
  CASE
    WHEN status = 'completed' THEN 0
    WHEN status = 'cancelled' THEN 0
    WHEN status NOT IN (
      'draft', 'availability_requested', 'availability_closed', 'plan_proposed',
      'plan_confirmed', 'in_progress'
    ) THEN 1
    ELSE 0
  END
FROM exam_round;

ALTER TABLE round_candidate ADD COLUMN terminal_status TEXT NOT NULL DEFAULT 'open'
  CHECK (terminal_status IN (
    'open', 'result_communicated', 'transferred', 'postponed', 'ihk_terminated'
  ));
ALTER TABLE round_candidate ADD COLUMN terminal_reason TEXT;
ALTER TABLE round_candidate ADD COLUMN effective_new_round_id INTEGER
  REFERENCES exam_round(id) ON DELETE RESTRICT;
ALTER TABLE round_candidate ADD COLUMN postponed_until TEXT;
ALTER TABLE round_candidate ADD COLUMN ihk_decision_reference TEXT;
ALTER TABLE round_candidate ADD COLUMN terminal_at TEXT;

CREATE TABLE exam_round_decision (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  decision_type TEXT NOT NULL CHECK (decision_type IN ('close', 'cancel')),
  requested_revision INTEGER NOT NULL CHECK (requested_revision >= 1),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision > requested_revision),
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  reason TEXT,
  checklist_json TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  previous_decision_id INTEGER REFERENCES exam_round_decision(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded')),
  command_fingerprint TEXT NOT NULL CHECK (length(command_fingerprint) = 64),
  decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, resulting_revision),
  UNIQUE (exam_round_id, command_fingerprint),
  CHECK (
    (decision_type = 'close' AND reason IS NULL)
    OR (decision_type = 'cancel' AND length(trim(reason)) > 0)
  )
);

CREATE TABLE exam_round_reopening (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  previous_decision_id INTEGER REFERENCES exam_round_decision(id) ON DELETE RESTRICT,
  requested_revision INTEGER NOT NULL CHECK (requested_revision >= 1),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision > requested_revision),
  occasion TEXT NOT NULL CHECK (length(trim(occasion)) > 0),
  source TEXT NOT NULL CHECK (length(trim(source)) > 0),
  reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  requested_scope_json TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  impacts_json TEXT NOT NULL,
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
  command_fingerprint TEXT NOT NULL CHECK (length(command_fingerprint) = 64),
  opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE (exam_round_id, command_fingerprint),
  CHECK (
    (status = 'open' AND completed_at IS NULL)
    OR (status = 'completed' AND completed_at IS NOT NULL)
  )
);

CREATE TABLE exam_round_task (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  reopening_id INTEGER NOT NULL REFERENCES exam_round_reopening(id) ON DELETE CASCADE,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  task_type TEXT NOT NULL CHECK (task_type IN (
    'reconfirmation', 'result_recommunication', 'ihk_clarification'
  )),
  origin_key TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE (recipient_member_id, task_type, origin_key)
);

CREATE TABLE exam_round_audit_event (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  round_revision INTEGER NOT NULL CHECK (round_revision >= 1),
  event_type TEXT NOT NULL CHECK (event_type IN (
    'closed', 'cancelled', 'reopened', 'reclosed', 'recancelled'
  )),
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  decision_id INTEGER REFERENCES exam_round_decision(id) ON DELETE RESTRICT,
  reopening_id INTEGER REFERENCES exam_round_reopening(id) ON DELETE RESTRICT,
  reason TEXT,
  scope_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exam_round_export (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  decision_id INTEGER REFERENCES exam_round_decision(id) ON DELETE RESTRICT,
  round_revision INTEGER NOT NULL CHECK (round_revision >= 1),
  export_kind TEXT NOT NULL CHECK (export_kind IN ('machine', 'human')),
  lifecycle_status TEXT NOT NULL CHECK (
    lifecycle_status IN ('open', 'closed', 'cancelled', 'reopening', 'historical')
  ),
  generated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  superseded_at TEXT,
  superseded_by_revision INTEGER
);

CREATE TABLE exam_round_ihk_status (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE RESTRICT,
  document_status TEXT NOT NULL CHECK (length(trim(document_status)) > 0),
  document_reference TEXT NOT NULL CHECK (length(trim(document_reference)) > 0),
  recorded_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  command_fingerprint TEXT NOT NULL UNIQUE CHECK (length(command_fingerprint) = 64),
  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX exam_round_decision_revision
  ON exam_round_decision(exam_round_id, resulting_revision);
CREATE INDEX exam_round_reopening_open
  ON exam_round_reopening(exam_round_id, status);
CREATE INDEX exam_round_task_round_status
  ON exam_round_task(exam_round_id, status);
CREATE INDEX exam_round_audit_history
  ON exam_round_audit_event(exam_round_id, id);
CREATE INDEX exam_round_export_history
  ON exam_round_export(exam_round_id, generated_at);
CREATE INDEX exam_round_ihk_status_history
  ON exam_round_ihk_status(exam_round_id, id);

CREATE TRIGGER exam_round_decision_immutable_update
BEFORE UPDATE ON exam_round_decision
WHEN NOT (
  OLD.status = 'current'
  AND NEW.status = 'superseded'
  AND NEW.id IS OLD.id
  AND NEW.exam_round_id IS OLD.exam_round_id
  AND NEW.decision_type IS OLD.decision_type
  AND NEW.requested_revision IS OLD.requested_revision
  AND NEW.resulting_revision IS OLD.resulting_revision
  AND NEW.actor_member_id IS OLD.actor_member_id
  AND NEW.reason IS OLD.reason
  AND NEW.checklist_json IS OLD.checklist_json
  AND NEW.snapshot_json IS OLD.snapshot_json
  AND NEW.previous_decision_id IS OLD.previous_decision_id
  AND NEW.command_fingerprint IS OLD.command_fingerprint
  AND NEW.decided_at IS OLD.decided_at
)
BEGIN
  SELECT RAISE(ABORT, 'exam round decision evidence is immutable');
END;

CREATE TRIGGER exam_round_decision_immutable_delete
BEFORE DELETE ON exam_round_decision
BEGIN
  SELECT RAISE(ABORT, 'exam round decision evidence is immutable');
END;

INSERT INTO schema_migration (name) VALUES ('023_add_exam_round_lifecycle.sql');
COMMIT;
