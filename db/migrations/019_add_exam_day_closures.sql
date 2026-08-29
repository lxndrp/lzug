-- Add revision-bound formal closure, targeted reopening, tasks, and history for exam days.
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

ALTER TABLE exam_day
  ADD COLUMN revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1);
ALTER TABLE exam_day
  ADD COLUMN closure_status TEXT NOT NULL DEFAULT 'open' CHECK (
    closure_status IN ('open', 'closed', 'closed_exception', 'reopening', 'historical')
  );

UPDATE exam_day
SET closure_status = 'historical'
WHERE status IN ('completed', 'cancelled');

CREATE TABLE exam_day_closure (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  requested_revision INTEGER NOT NULL CHECK (requested_revision >= 1),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision > requested_revision),
  closure_type TEXT NOT NULL CHECK (closure_type IN ('regular', 'exception')),
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  reason TEXT,
  clarification_attempts TEXT,
  checklist_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  protocol_references_json TEXT NOT NULL,
  result_references_json TEXT NOT NULL,
  previous_closure_id INTEGER REFERENCES exam_day_closure(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded')),
  command_fingerprint TEXT NOT NULL CHECK (length(command_fingerprint) = 64),
  closed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_day_id, resulting_revision),
  UNIQUE (exam_day_id, command_fingerprint),
  CHECK (
    (closure_type = 'regular' AND reason IS NULL AND clarification_attempts IS NULL)
    OR (
      closure_type = 'exception'
      AND length(trim(reason)) > 0
      AND length(trim(clarification_attempts)) > 0
    )
  )
);

CREATE TABLE exam_day_reopening (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  previous_closure_id INTEGER REFERENCES exam_day_closure(id) ON DELETE RESTRICT,
  requested_revision INTEGER NOT NULL CHECK (requested_revision >= 1),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision > requested_revision),
  occasion TEXT NOT NULL CHECK (length(trim(occasion)) > 0),
  source TEXT NOT NULL CHECK (length(trim(source)) > 0),
  reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  requested_scope_json TEXT NOT NULL,
  scope_json TEXT NOT NULL,
  completed_scope_json TEXT NOT NULL DEFAULT '[]',
  impacts_json TEXT NOT NULL,
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
  command_fingerprint TEXT NOT NULL CHECK (length(command_fingerprint) = 64),
  opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE (exam_day_id, command_fingerprint),
  CHECK (
    (status = 'open' AND completed_at IS NULL)
    OR (status = 'completed' AND completed_at IS NOT NULL)
  )
);

CREATE TABLE exam_day_task (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  reopening_id INTEGER REFERENCES exam_day_reopening(id) ON DELETE CASCADE,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  task_type TEXT NOT NULL CHECK (task_type IN (
    'protocol_follow_up', 'protocol_reconfirmation', 'result_reconfirmation',
    'result_recommunication', 'ihk_clarification'
  )),
  origin_key TEXT NOT NULL,
  exam_protocol_revision_id INTEGER REFERENCES exam_protocol_revision(id) ON DELETE RESTRICT,
  result_determination_id INTEGER REFERENCES result_determination(id) ON DELETE RESTRICT,
  details_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE (recipient_member_id, task_type, origin_key),
  CHECK (
    (status = 'open' AND completed_at IS NULL)
    OR (status = 'completed' AND completed_at IS NOT NULL)
  )
);

CREATE TABLE exam_day_audit_event (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  day_revision INTEGER NOT NULL CHECK (day_revision >= 1),
  event_type TEXT NOT NULL CHECK (event_type IN (
    'closed', 'closed_exception', 'reopened', 'correction',
    'late_protocol_response', 'reclosed'
  )),
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  closure_id INTEGER REFERENCES exam_day_closure(id) ON DELETE RESTRICT,
  reopening_id INTEGER REFERENCES exam_day_reopening(id) ON DELETE RESTRICT,
  reason TEXT,
  scope_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exam_day_export (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  closure_id INTEGER REFERENCES exam_day_closure(id) ON DELETE RESTRICT,
  export_kind TEXT NOT NULL CHECK (export_kind IN ('machine', 'human')),
  status TEXT NOT NULL CHECK (
    status IN ('open', 'closed', 'closed_exception', 'reopening', 'historical')
  ),
  generated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX exam_day_closure_revision
  ON exam_day_closure(exam_day_id, resulting_revision);
CREATE INDEX exam_day_reopening_open
  ON exam_day_reopening(exam_day_id, status);
CREATE INDEX exam_day_task_day_status
  ON exam_day_task(exam_day_id, status);
CREATE INDEX exam_day_audit_history
  ON exam_day_audit_event(exam_day_id, id);
CREATE INDEX exam_day_export_history
  ON exam_day_export(exam_day_id, generated_at);

-- Extend the bounded notification event set without losing queued deliveries.
DROP INDEX notification_recipient_created;
DROP INDEX notification_committee_created;
DROP INDEX notification_delivery_due;
ALTER TABLE notification_delivery RENAME TO notification_delivery_legacy;
ALTER TABLE notification RENAME TO notification_legacy;

CREATE TABLE notification (
  id INTEGER PRIMARY KEY,
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
  exam_round_id INTEGER REFERENCES exam_round(id) ON DELETE CASCADE,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'availability_requested', 'availability_reminder',
    'availability_deadline_expired', 'plan_confirmed', 'synthetic_test',
    'examiner_absence_reported', 'fallback_confirmation_requested',
    'fallback_confirmation_expired', 'replacement_requested',
    'urgent_replacement_requested', 'replacement_selected',
    'exam_day_cancelled', 'absence_reopened',
    'exam_day_protocol_follow_up', 'exam_day_reopened', 'exam_day_reclosed',
    'exam_day_result_recommunication', 'exam_day_ihk_clarification'
  )),
  origin_key TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  action_path TEXT NOT NULL CHECK (action_path LIKE '/%'),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (recipient_member_id, event_type, origin_key)
);

INSERT INTO notification (
  id, committee_id, exam_round_id, recipient_member_id, event_type,
  origin_key, title, message, action_path, created_at
)
SELECT
  id, committee_id, exam_round_id, recipient_member_id, event_type,
  origin_key, title, message, action_path, created_at
FROM notification_legacy;

CREATE TABLE notification_delivery (
  id INTEGER PRIMARY KEY,
  notification_id INTEGER NOT NULL REFERENCES notification(id) ON DELETE CASCADE,
  channel TEXT NOT NULL CHECK (channel IN ('web_push', 'email', 'sink')),
  target_key TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'pending', 'technically_confirmed', 'temporarily_failed',
    'permanently_failed', 'unavailable'
  )),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TEXT,
  technical_confirmed_at TEXT,
  error_code TEXT,
  claim_token TEXT,
  claimed_at TEXT,
  claim_expires_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (notification_id, channel, target_key),
  CHECK (
    (claim_token IS NULL AND claimed_at IS NULL AND claim_expires_at IS NULL)
    OR (
      claim_token IS NOT NULL
      AND claimed_at IS NOT NULL
      AND claim_expires_at IS NOT NULL
      AND claim_expires_at > claimed_at
    )
  )
);

INSERT INTO notification_delivery (
  id, notification_id, channel, target_key, status, attempt_count,
  next_attempt_at, technical_confirmed_at, error_code, claim_token,
  claimed_at, claim_expires_at, created_at, updated_at
)
SELECT
  id, notification_id, channel, target_key, status, attempt_count,
  next_attempt_at, technical_confirmed_at, error_code, claim_token,
  claimed_at, claim_expires_at, created_at, updated_at
FROM notification_delivery_legacy;

DROP TABLE notification_delivery_legacy;
DROP TABLE notification_legacy;

CREATE INDEX notification_recipient_created
  ON notification(recipient_member_id, created_at DESC, id DESC);
CREATE INDEX notification_committee_created
  ON notification(committee_id, created_at DESC, id DESC);
CREATE INDEX notification_delivery_due
  ON notification_delivery(status, next_attempt_at, claim_expires_at, id);

INSERT INTO schema_migration (name) VALUES ('019_add_exam_day_closures.sql');
COMMIT;
PRAGMA foreign_keys = ON;
