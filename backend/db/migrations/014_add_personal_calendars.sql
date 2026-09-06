-- Add personal, token-protected calendar feeds and versioned ICS event snapshots.
BEGIN TRANSACTION;

CREATE TABLE calendar_feed (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL UNIQUE REFERENCES person(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revoked_at TEXT,
  CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

ALTER TABLE calendar_event RENAME TO calendar_event_legacy;
DROP INDEX IF EXISTS calendar_event_status;

CREATE TABLE calendar_event (
  id INTEGER PRIMARY KEY,
  external_event_id TEXT NOT NULL UNIQUE,
  exam_half_year_id INTEGER NOT NULL REFERENCES exam_half_year(id) ON DELETE RESTRICT,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE RESTRICT,
  exam_day_id INTEGER REFERENCES exam_day(id) ON DELETE SET NULL,
  exam_day_assignment_id INTEGER REFERENCES exam_day_assignment(id) ON DELETE SET NULL,
  recipient_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  starts_at TEXT NOT NULL,
  ends_at TEXT NOT NULL,
  time_zone TEXT NOT NULL,
  location TEXT NOT NULL,
  role TEXT NOT NULL,
  round_name TEXT NOT NULL,
  secure_reference TEXT NOT NULL CHECK (secure_reference LIKE '/%'),
  source_key TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'updated', 'cancelled')),
  content_hash TEXT NOT NULL CHECK (length(content_hash) = 64),
  sent_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO calendar_event (
  id, external_event_id, exam_half_year_id, exam_round_id, exam_day_id,
  recipient_member_id, date, starts_at, ends_at, time_zone, location, role,
  round_name, secure_reference, source_key, version, status, content_hash,
  sent_at, created_at, updated_at
)
SELECT
  legacy.id,
  'legacy-' || legacy.id,
  round.exam_half_year_id,
  round.id,
  COALESCE(legacy.exam_day_id, slot.exam_day_id),
  legacy.recipient_member_id,
  COALESCE(day.date, substr(slot.starts_at, 1, 10), '1970-01-01'),
  COALESCE(slot.starts_at, COALESCE(day.date, '1970-01-01') || ' 00:00:00'),
  COALESCE(slot.ends_at, COALESCE(day.date, '1970-01-01') || ' 23:59:59'),
  'Europe/Berlin',
  COALESCE(location.name || ', ' || location.room || ', ' || location.postal_code || ' ' || location.city, ''),
  'Prüfer',
  round.name,
  '/api/confirmed-plan-days/' || COALESCE(legacy.exam_day_id, slot.exam_day_id),
  'legacy:' || legacy.id,
  1,
  CASE WHEN legacy.status = 'cancelled' THEN 'cancelled' ELSE 'sent' END,
  printf('%064d', legacy.id),
  legacy.sent_at,
  legacy.created_at,
  legacy.updated_at
FROM calendar_event_legacy AS legacy
LEFT JOIN exam_day AS day ON day.id = legacy.exam_day_id
LEFT JOIN exam_slot AS slot ON slot.id = legacy.exam_slot_id
LEFT JOIN exam_day AS slot_day ON slot_day.id = slot.exam_day_id
JOIN exam_round AS round
  ON round.id = COALESCE(day.exam_round_id, slot_day.exam_round_id)
LEFT JOIN location ON location.id = COALESCE(day.location_id, slot_day.location_id)
WHERE legacy.recipient_member_id IS NOT NULL;

DROP TABLE calendar_event_legacy;

CREATE INDEX calendar_event_source ON calendar_event(source_key);
CREATE INDEX calendar_event_recipient_period
  ON calendar_event(recipient_member_id, exam_half_year_id);
CREATE INDEX calendar_event_status ON calendar_event(status);

INSERT INTO schema_migration (name) VALUES ('014_add_personal_calendars.sql');
COMMIT;
