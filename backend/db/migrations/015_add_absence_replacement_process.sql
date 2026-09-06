-- Add the auditable absence/replacement process and its notification events.
BEGIN TRANSACTION;

ALTER TABLE absence_report ADD COLUMN exam_day_assignment_id INTEGER REFERENCES exam_day_assignment(id) ON DELETE RESTRICT;
ALTER TABLE absence_report ADD COLUMN reported_by_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT;
ALTER TABLE absence_report ADD COLUMN version INTEGER NOT NULL DEFAULT 0;

ALTER TABLE replacement_response ADD COLUMN requested_at TEXT NOT NULL DEFAULT '';
ALTER TABLE replacement_response ADD COLUMN expires_at TEXT;
ALTER TABLE replacement_response ADD COLUMN urgent INTEGER NOT NULL DEFAULT 0 CHECK (urgent IN (0, 1));

CREATE TABLE absence_audit_event (
  id INTEGER PRIMARY KEY,
  absence_report_id INTEGER NOT NULL REFERENCES absence_report(id) ON DELETE CASCADE,
  actor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  event_type TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT,
  details TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX absence_audit_report_created
  ON absence_audit_event(absence_report_id, created_at);

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
    'exam_day_cancelled', 'absence_reopened'
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
SELECT id, committee_id, exam_round_id, recipient_member_id, event_type,
       origin_key, title, message, action_path, created_at
FROM notification_legacy;

DROP TABLE notification_legacy;

CREATE INDEX notification_recipient_created
  ON notification(recipient_member_id, created_at DESC, id DESC);
CREATE INDEX notification_committee_created
  ON notification(committee_id, created_at DESC, id DESC);

INSERT INTO schema_migration (name) VALUES ('015_add_absence_replacement_process.sql');
COMMIT;
