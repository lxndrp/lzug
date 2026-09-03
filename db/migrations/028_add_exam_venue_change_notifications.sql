-- Add the domain notification emitted for meaningful future venue changes.
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

DROP INDEX notification_delivery_due;
DROP INDEX notification_recipient_created;
DROP INDEX notification_committee_created;

ALTER TABLE notification_delivery RENAME TO notification_delivery_legacy_027;
ALTER TABLE notification RENAME TO notification_legacy_027;

CREATE TABLE notification (
  id INTEGER PRIMARY KEY,
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
  exam_round_id INTEGER REFERENCES exam_round(id) ON DELETE CASCADE,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'availability_requested', 'availability_reminder',
    'availability_deadline_expired', 'plan_confirmed', 'plan_changed', 'synthetic_test',
    'examiner_absence_reported', 'fallback_confirmation_requested',
    'fallback_confirmation_expired', 'replacement_requested',
    'urgent_replacement_requested', 'replacement_selected',
    'exam_day_cancelled', 'absence_reopened',
    'exam_day_protocol_follow_up', 'exam_day_reopened', 'exam_day_reclosed',
    'exam_day_result_recommunication', 'exam_day_ihk_clarification',
    'exam_venue_changed'
  )),
  origin_key TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  action_path TEXT NOT NULL CHECK (action_path LIKE '/%'),
  superseded_at TEXT,
  superseded_by_revision_id INTEGER
    REFERENCES confirmed_plan_revision(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (recipient_member_id, event_type, origin_key)
);

INSERT INTO notification (
  id, committee_id, exam_round_id, recipient_member_id, event_type,
  origin_key, title, message, action_path, superseded_at,
  superseded_by_revision_id, created_at
)
SELECT
  id, committee_id, exam_round_id, recipient_member_id, event_type,
  origin_key, title, message, action_path, superseded_at,
  superseded_by_revision_id, created_at
FROM notification_legacy_027;

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
  next_attempt_at, technical_confirmed_at, error_code,
  claim_token, claimed_at, claim_expires_at, created_at, updated_at
)
SELECT
  id, notification_id, channel, target_key, status, attempt_count,
  next_attempt_at, technical_confirmed_at, error_code,
  claim_token, claimed_at, claim_expires_at, created_at, updated_at
FROM notification_delivery_legacy_027;

DROP TABLE notification_delivery_legacy_027;
DROP TABLE notification_legacy_027;

CREATE INDEX notification_recipient_created
  ON notification(recipient_member_id, created_at DESC, id DESC);
CREATE INDEX notification_committee_created
  ON notification(committee_id, created_at DESC, id DESC);
CREATE INDEX notification_delivery_due
  ON notification_delivery(status, next_attempt_at, claim_expires_at, id);

INSERT INTO schema_migration (name)
VALUES ('028_add_exam_venue_change_notifications.sql');

COMMIT;
PRAGMA foreign_keys = ON;
