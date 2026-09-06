-- Add the channel-neutral notification contract and technical delivery state.
BEGIN TRANSACTION;

ALTER TABLE notification RENAME TO notification_legacy;

CREATE TABLE notification (
  id INTEGER PRIMARY KEY,
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
  exam_round_id INTEGER REFERENCES exam_round(id) ON DELETE CASCADE,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'availability_requested', 'availability_reminder',
    'availability_deadline_expired', 'plan_confirmed', 'synthetic_test'
  )),
  origin_key TEXT NOT NULL,
  title TEXT NOT NULL,
  message TEXT NOT NULL,
  action_path TEXT NOT NULL CHECK (action_path LIKE '/%'),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (recipient_member_id, event_type, origin_key)
);

CREATE INDEX notification_recipient_created
  ON notification(recipient_member_id, created_at DESC, id DESC);
CREATE INDEX notification_committee_created
  ON notification(committee_id, created_at DESC, id DESC);

CREATE TABLE push_subscription (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL UNIQUE CHECK (endpoint LIKE 'https://%'),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  invalidated_at TEXT
);

CREATE INDEX push_subscription_person_active
  ON push_subscription(person_id, invalidated_at);

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
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (notification_id, channel, target_key)
);

CREATE INDEX notification_delivery_due
  ON notification_delivery(status, next_attempt_at);

INSERT OR IGNORE INTO notification
  (committee_id, exam_round_id, recipient_member_id, event_type, origin_key,
   title, message, action_path, created_at)
SELECT
  exam_round.committee_id,
  notification_legacy.exam_round_id,
  notification_legacy.recipient_member_id,
  CASE notification_legacy.notification_type
    WHEN 'availability_deadline_missed' THEN 'availability_deadline_expired'
    ELSE notification_legacy.notification_type
  END,
  'legacy-notification:' || notification_legacy.id,
  notification_legacy.subject,
  notification_legacy.body,
  CASE notification_legacy.notification_type
    WHEN 'plan_confirmed' THEN '/confirmed-plans/' || notification_legacy.exam_round_id
    ELSE '/scheduling-overview/' || notification_legacy.exam_round_id
  END,
  notification_legacy.created_at
FROM notification_legacy
JOIN exam_round ON exam_round.id = notification_legacy.exam_round_id
WHERE notification_legacy.recipient_member_id IS NOT NULL
  AND notification_legacy.notification_type IN (
    'availability_requested', 'availability_reminder',
    'availability_deadline_missed', 'plan_confirmed'
  );

DROP TABLE notification_legacy;

INSERT INTO schema_migration (name) VALUES ('013_add_notifications.sql');
COMMIT;
