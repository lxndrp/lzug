-- Derive and process notification and calendar consequences after plan revisions.
BEGIN TRANSACTION;

DROP INDEX notification_delivery_due;
DROP INDEX notification_recipient_created;
DROP INDEX notification_committee_created;

ALTER TABLE notification_delivery RENAME TO notification_delivery_legacy_021;
ALTER TABLE notification RENAME TO notification_legacy_021;

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
    'exam_day_result_recommunication', 'exam_day_ihk_clarification'
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
  origin_key, title, message, action_path, created_at
)
SELECT
  id, committee_id, exam_round_id, recipient_member_id, event_type,
  origin_key, title, message, action_path, created_at
FROM notification_legacy_021;

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
FROM notification_delivery_legacy_021;

DROP TABLE notification_delivery_legacy_021;
DROP TABLE notification_legacy_021;

CREATE INDEX notification_recipient_created
  ON notification(recipient_member_id, created_at DESC, id DESC);
CREATE INDEX notification_committee_created
  ON notification(committee_id, created_at DESC, id DESC);
CREATE INDEX notification_delivery_due
  ON notification_delivery(status, next_attempt_at, claim_expires_at, id);

CREATE TABLE plan_consequence_batch (
  id INTEGER PRIMARY KEY,
  origin_type TEXT NOT NULL CHECK (length(trim(origin_type)) > 0),
  origin_key TEXT NOT NULL CHECK (length(trim(origin_key)) > 0),
  confirmed_plan_revision_id INTEGER UNIQUE
    REFERENCES confirmed_plan_revision(id) ON DELETE CASCADE,
  notification_scope_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending', 'succeeded', 'temporarily_failed', 'permanently_failed'
  )),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TEXT,
  error_code TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX plan_consequence_batch_origin
  ON plan_consequence_batch(origin_type, origin_key);

CREATE TABLE plan_consequence (
  id INTEGER PRIMARY KEY,
  batch_id INTEGER NOT NULL REFERENCES plan_consequence_batch(id) ON DELETE CASCADE,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  consequence_type TEXT NOT NULL CHECK (consequence_type IN ('notification', 'calendar')),
  action TEXT NOT NULL CHECK (action IN ('notify', 'create', 'update', 'cancel')),
  identity_key TEXT NOT NULL CHECK (length(trim(identity_key)) > 0),
  details_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
    'pending', 'succeeded', 'temporarily_failed', 'permanently_failed', 'superseded'
  )),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  next_attempt_at TEXT,
  error_code TEXT,
  calendar_event_id INTEGER REFERENCES calendar_event(id) ON DELETE SET NULL,
  calendar_event_version INTEGER CHECK (
    calendar_event_version IS NULL OR calendar_event_version >= 1
  ),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (
    batch_id, recipient_member_id, consequence_type, identity_key
  )
);

CREATE INDEX plan_consequence_due
  ON plan_consequence(status, next_attempt_at, id);

-- Existing revisions predate the consequence processor. Mark their derivation as
-- intentionally not replayed so scheduled processing cannot emit historical effects.
-- A selected revision can still be re-derived through the controlled retry path.
INSERT INTO plan_consequence_batch (
  origin_type, origin_key, confirmed_plan_revision_id,
  notification_scope_json, status, attempt_count, error_code
)
SELECT
  'confirmed_plan_revision', CAST(id AS TEXT), id,
  '[]', 'succeeded', 0, 'migration_not_replayed'
FROM confirmed_plan_revision;

INSERT INTO schema_migration (name) VALUES ('022_add_plan_consequences.sql');
COMMIT;
