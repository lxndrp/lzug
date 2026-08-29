-- lzug relationales Basisschema
-- Stand: 2026-08-29
--
-- Ziel:
-- - möglichst PostgreSQL-kompatibel
-- - für eine frühe Server-Version auch mit SQLite nutzbar
-- - fachliche Enums zunächst als TEXT + CHECK modelliert

PRAGMA foreign_keys = ON;

CREATE TABLE schema_migration (
  name TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO schema_migration (name)
VALUES ('001_add_holiday_planning_settings.sql'), ('002_add_person_memberships.sql'),
       ('003_add_exam_half_years.sql'), ('004_add_candidate_committee_assignments.sql'),
       ('005_add_exam_day_attendance.sql'), ('006_add_exam_execution_status.sql'),
       ('007_add_documents.sql'), ('008_add_authentication_sessions.sql'),
       ('009_harden_migration_history.sql'), ('010_add_operator_auth_tokens.sql'),
       ('011_add_local_password_totp_auth.sql'),
       ('012_add_plan_revision.sql'), ('013_add_notifications.sql'),
       ('014_add_personal_calendars.sql'), ('015_add_absence_replacement_process.sql'),
       ('016_claim_notification_deliveries.sql');

CREATE TABLE schema_migration_checksum (
  name TEXT PRIMARY KEY REFERENCES schema_migration(name) ON DELETE CASCADE,
  checksum TEXT NOT NULL CHECK (length(checksum) = 64)
);

INSERT INTO schema_migration_checksum (name, checksum) VALUES
  ('001_add_holiday_planning_settings.sql', '50841191962f8c054b2c78863e30a2566a9d42d901f2469df24b6882bd32aaa1'),
  ('002_add_person_memberships.sql', 'f6e2b7b3221cdff240b24c3f28f41b63cfb39a1d0b9a5ba323512245f547f8d0'),
  ('003_add_exam_half_years.sql', 'e81323a22ef990782df6eb193c66b23f70ec269f3b06d17885bf77bf5345c67b'),
  ('004_add_candidate_committee_assignments.sql', '66554074e75ad0668b08761ef725b84623ba7d6193fb0b6dbc403f7b0ac48a17'),
  ('005_add_exam_day_attendance.sql', 'd9282f45a0d2abf28dd67361983789410146b842fec1f92a8af3d2b29225d34c'),
  ('006_add_exam_execution_status.sql', '63686ec8511d0224bb1365d3fc00f432bcc897a9ae2927cfeee74c05d45f87a5'),
  ('007_add_documents.sql', '6b1b5ae1dd9b954b3d7bc139afb03c4b977f50ef187e4fe50bd1aaf21d35b95c'),
  ('008_add_authentication_sessions.sql', '926452905ea280e06b805b78a7074143e02a0d2439cd2d37ce1727e0ace3026c'),
  ('009_harden_migration_history.sql', 'a71425eb5cd8674532cd8c05672fb28c977b86c27dac610ade1e57964c9ba7a1'),
  ('010_add_operator_auth_tokens.sql', '6e0f3400d0871ddee4ec840360990f6b6fcd5ac8233f67c31cf03d2c4499e25a'),
  ('011_add_local_password_totp_auth.sql', '7f17cd3e4b2eb0f359c4e55902f0e5f25068703d804d9d6279597770beb6eef1'),
  ('012_add_plan_revision.sql', 'e9462145b627eb238219d728d2b1263dd16e6d5eb30d33dbb1f7f0c61226e8fb'),
  ('013_add_notifications.sql', '6cacc994e8b4356ce9b1639a7df48efd046c66f083d14dc77f8ed2007851276e'),
  ('014_add_personal_calendars.sql', '68b46cd341c21ec12a8d08ba75b35b1215eaa04e992140841db501b8250ac635'),
  ('015_add_absence_replacement_process.sql', 'd9b07a0fcca65202c1fc68b0874718551924624ac26517339a253e73394d9829'),
  ('016_claim_notification_deliveries.sql', '3f6d7e71512af61da4669ff7b320b7093a32f0553b657aa89dc0b85ac8693bcb');

CREATE TABLE committee (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  occupation TEXT NOT NULL DEFAULT 'Fachinformatiker/in',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE person (
  id INTEGER PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT NOT NULL COLLATE NOCASE UNIQUE,
  mobile TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE committee_member (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE RESTRICT,
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
  member_status TEXT NOT NULL CHECK (member_status IN ('ordinary', 'deputy')),
  committee_role TEXT NOT NULL CHECK (committee_role IN ('chair', 'deputy_chair', 'member')),
  representing_side TEXT NOT NULL CHECK (representing_side IN ('employer', 'employee', 'school')),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (committee_id, person_id)
);

CREATE UNIQUE INDEX committee_member_one_chair_per_committee
  ON committee_member(committee_id)
  WHERE committee_role = 'chair';

CREATE UNIQUE INDEX committee_member_one_deputy_chair_per_committee
  ON committee_member(committee_id)
  WHERE committee_role = 'deputy_chair';

CREATE TABLE user_account (
  id INTEGER PRIMARY KEY,
  person_id INTEGER UNIQUE REFERENCES person(id) ON DELETE SET NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  passkey_enabled INTEGER NOT NULL DEFAULT 0 CHECK (passkey_enabled IN (0, 1)),
  two_factor_enabled INTEGER NOT NULL DEFAULT 0 CHECK (two_factor_enabled IN (0, 1)),
  is_operator INTEGER NOT NULL DEFAULT 0 CHECK (is_operator IN (0, 1)),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  last_login_at TEXT,
  totp_secret_encrypted TEXT,
  totp_last_step INTEGER,
  totp_enabled INTEGER NOT NULL DEFAULT 0 CHECK (totp_enabled IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (two_factor_enabled = 0 OR passkey_enabled = 1)
);

CREATE UNIQUE INDEX user_account_one_operator
  ON user_account(is_operator)
  WHERE is_operator = 1;

CREATE TABLE auth_session (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revoked_at TEXT,
  revoke_reason TEXT,
  rotated_from_id INTEGER REFERENCES auth_session(id) ON DELETE SET NULL,
  CHECK (expires_at > created_at),
  CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE INDEX auth_session_account_active
  ON auth_session(account_id, revoked_at, expires_at);

CREATE TABLE auth_token (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('invitation', 'recovery')),
  token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  consumed_at TEXT,
  CHECK (expires_at > created_at),
  CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX auth_token_account_kind
  ON auth_token(account_id, kind, expires_at);

CREATE TABLE auth_recovery_code (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
  code_hash TEXT NOT NULL CHECK (length(code_hash) >= 64),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  consumed_at TEXT,
  CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX auth_recovery_code_account_active
  ON auth_recovery_code(account_id, consumed_at);

CREATE TABLE location (
  id INTEGER PRIMARY KEY,
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  street TEXT NOT NULL,
  postal_code TEXT NOT NULL,
  city TEXT NOT NULL,
  room TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE candidate (
  id INTEGER PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  ihk_exam_number TEXT NOT NULL UNIQUE,
  specialization TEXT NOT NULL CHECK (
    specialization IN (
      'application_development',
      'system_integration',
      'data_and_process_analysis',
      'digital_networking'
    )
  ),
  training_company TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exam_half_year (
  id INTEGER PRIMARY KEY,
  season TEXT NOT NULL CHECK (season IN ('summer', 'winter')),
  year INTEGER NOT NULL CHECK (year BETWEEN 2000 AND 2100),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'completed', 'archived')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (season, year)
);

CREATE TABLE exam_round (
  id INTEGER PRIMARY KEY,
  exam_half_year_id INTEGER NOT NULL REFERENCES exam_half_year(id) ON DELETE RESTRICT,
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (
    status IN (
      'draft',
      'availability_requested',
      'availability_closed',
      'plan_proposed',
      'plan_confirmed',
      'in_progress',
      'completed',
      'cancelled'
    )
  ),
  plan_revision INTEGER NOT NULL DEFAULT 0 CHECK (plan_revision >= 0),
  availability_deadline TEXT,
  availability_reminder_at TEXT,
  created_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (committee_id, name),
  UNIQUE (exam_half_year_id, committee_id),
  CHECK (
    availability_deadline IS NULL
    OR availability_reminder_at IS NULL
    OR availability_reminder_at <= availability_deadline
  )
);

CREATE TABLE round_candidate (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  candidate_id INTEGER NOT NULL REFERENCES candidate(id) ON DELETE RESTRICT,
  attempt_number INTEGER NOT NULL CHECK (attempt_number >= 1),
  requires_mep INTEGER NOT NULL DEFAULT 0 CHECK (requires_mep IN (0, 1)),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, candidate_id)
);

CREATE TABLE candidate_committee_assignment (
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER NOT NULL REFERENCES candidate(id) ON DELETE RESTRICT,
  exam_half_year_id INTEGER NOT NULL REFERENCES exam_half_year(id) ON DELETE RESTRICT,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE RESTRICT,
  round_candidate_id INTEGER NOT NULL REFERENCES round_candidate(id) ON DELETE RESTRICT,
  assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ended_at TEXT,
  change_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (ended_at IS NULL OR ended_at >= assigned_at)
);

CREATE UNIQUE INDEX candidate_committee_assignment_one_active_per_half_year
  ON candidate_committee_assignment(candidate_id, exam_half_year_id)
  WHERE ended_at IS NULL;

CREATE INDEX candidate_committee_assignment_history
  ON candidate_committee_assignment(candidate_id, exam_half_year_id, assigned_at DESC);

CREATE TABLE planning_settings (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL UNIQUE REFERENCES exam_round(id) ON DELETE CASCADE,
  calendar_week_from TEXT NOT NULL,
  calendar_week_to TEXT NOT NULL,
  exams_per_day INTEGER NOT NULL CHECK (exams_per_day >= 1),
  max_exam_days_per_week INTEGER NOT NULL DEFAULT 3 CHECK (max_exam_days_per_week BETWEEN 1 AND 5),
  lunch_break_enabled INTEGER NOT NULL DEFAULT 1 CHECK (lunch_break_enabled IN (0, 1)),
  exclude_public_holidays INTEGER NOT NULL DEFAULT 0 CHECK (exclude_public_holidays IN (0, 1)),
  holiday_subdivision_code TEXT,
  default_location_id INTEGER REFERENCES location(id) ON DELETE SET NULL,
  updated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (calendar_week_from <= calendar_week_to),
  CHECK (
    holiday_subdivision_code IS NULL
    OR holiday_subdivision_code IN (
      'DE-BB', 'DE-BE', 'DE-BW', 'DE-BY', 'DE-HB', 'DE-HE', 'DE-HH', 'DE-MV',
      'DE-NI', 'DE-NW', 'DE-RP', 'DE-SH', 'DE-SL', 'DE-SN', 'DE-ST', 'DE-TH'
    )
  ),
  CHECK (exclude_public_holidays = 0 OR holiday_subdivision_code IS NOT NULL)
);

CREATE TABLE candidate_exam_day (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, date)
);

CREATE TABLE member_availability (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  candidate_exam_day_id INTEGER NOT NULL REFERENCES candidate_exam_day(id) ON DELETE CASCADE,
  availability TEXT NOT NULL DEFAULT 'pending' CHECK (
    availability IN ('full_day', 'morning', 'afternoon', 'unavailable', 'pending')
  ),
  responded_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, committee_member_id, candidate_exam_day_id),
  CHECK (
    availability = 'pending'
    OR responded_at IS NOT NULL
  )
);

CREATE TABLE exam_day (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  location_id INTEGER NOT NULL REFERENCES location(id) ON DELETE RESTRICT,
  date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (
    status IN ('proposed', 'confirmed', 'changed', 'cancelled', 'completed')
  ),
  lunch_break_enabled INTEGER NOT NULL DEFAULT 1 CHECK (lunch_break_enabled IN (0, 1)),
  created_from_proposal INTEGER NOT NULL DEFAULT 1 CHECK (created_from_proposal IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, date)
);

CREATE TABLE exam_slot (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  round_candidate_id INTEGER NOT NULL REFERENCES round_candidate(id) ON DELETE RESTRICT,
  slot_type TEXT NOT NULL CHECK (slot_type IN ('regular', 'mep')),
  starts_at TEXT NOT NULL,
  ends_at TEXT NOT NULL,
  sequence_number INTEGER NOT NULL CHECK (sequence_number >= 1),
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (
    status IN ('proposed', 'confirmed', 'rescheduled', 'cancelled', 'completed')
  ),
  actual_started_at TEXT,
  execution_status TEXT NOT NULL DEFAULT 'open' CHECK (
    execution_status IN ('open', 'running', 'completed', 'cancelled', 'needs_follow_up')
  ),
  status_changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actual_completed_at TEXT,
  status_reason TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_day_id, sequence_number),
  UNIQUE (round_candidate_id, slot_type),
  CHECK (ends_at > starts_at)
);

CREATE INDEX exam_slot_day_type_sequence
  ON exam_slot(exam_day_id, slot_type, sequence_number);

CREATE TABLE exam_day_assignment (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  assignment_role TEXT NOT NULL CHECK (assignment_role IN ('examiner', 'fallback')),
  day_part TEXT NOT NULL CHECK (day_part IN ('morning', 'afternoon', 'full_day')),
  fallback_status TEXT CHECK (
    fallback_status IS NULL
    OR fallback_status IN ('not_required', 'requested', 'confirmed', 'declined', 'expired')
  ),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_day_id, committee_member_id, assignment_role, day_part),
  CHECK (
    (assignment_role = 'fallback' AND fallback_status IS NOT NULL)
    OR (assignment_role = 'examiner' AND (fallback_status IS NULL OR fallback_status = 'not_required'))
  )
);

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

CREATE TABLE document (
  id INTEGER PRIMARY KEY,
  storage_id TEXT NOT NULL UNIQUE,
  original_filename TEXT NOT NULL,
  media_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
  checksum_sha256 TEXT NOT NULL CHECK (length(checksum_sha256) = 64),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX member_exam_attendance_day_status
  ON member_exam_attendance(exam_day_id, status);

CREATE TABLE absence_report (
  id INTEGER PRIMARY KEY,
  exam_day_id INTEGER NOT NULL REFERENCES exam_day(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  reported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'reported' CHECK (
    status IN (
      'reported',
      'fallback_requested',
      'fallback_confirmed',
      'fallback_expired',
      'replacement_requested',
      'replacement_selected',
      'no_replacement_available',
      'exam_day_cancelled',
      'resolved',
      'withdrawn'
    )
  ),
  exam_day_assignment_id INTEGER NOT NULL REFERENCES exam_day_assignment(id) ON DELETE RESTRICT,
  reported_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  selected_replacement_member_id INTEGER REFERENCES committee_member(id) ON DELETE SET NULL,
  version INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE replacement_response (
  id INTEGER PRIMARY KEY,
  absence_report_id INTEGER NOT NULL REFERENCES absence_report(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  response TEXT NOT NULL DEFAULT 'pending' CHECK (response IN ('pending', 'available', 'unavailable')),
  requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT,
  urgent INTEGER NOT NULL DEFAULT 0 CHECK (urgent IN (0, 1)),
  responded_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (absence_report_id, committee_member_id),
  CHECK (response = 'pending' OR responded_at IS NOT NULL)
);

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

CREATE TABLE push_subscription (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL REFERENCES person(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL UNIQUE CHECK (endpoint LIKE 'https://%'),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  invalidated_at TEXT
);

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

CREATE TABLE calendar_feed (
  id INTEGER PRIMARY KEY,
  person_id INTEGER NOT NULL UNIQUE REFERENCES person(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revoked_at TEXT,
  CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

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

CREATE INDEX committee_member_committee_active
  ON committee_member(committee_id, is_active);

CREATE INDEX committee_member_person
  ON committee_member(person_id);

CREATE INDEX candidate_name
  ON candidate(last_name, first_name);

CREATE INDEX exam_round_committee_status
  ON exam_round(committee_id, status);

CREATE INDEX round_candidate_round
  ON round_candidate(exam_round_id);

CREATE INDEX candidate_exam_day_round_date
  ON candidate_exam_day(exam_round_id, date);

CREATE INDEX member_availability_day
  ON member_availability(candidate_exam_day_id, availability);

CREATE INDEX exam_day_round_date
  ON exam_day(exam_round_id, date);

CREATE INDEX exam_day_assignment_day_part
  ON exam_day_assignment(exam_day_id, day_part, assignment_role);

CREATE INDEX notification_recipient_created
  ON notification(recipient_member_id, created_at DESC, id DESC);
CREATE INDEX notification_committee_created
  ON notification(committee_id, created_at DESC, id DESC);
CREATE INDEX push_subscription_person_active
  ON push_subscription(person_id, invalidated_at);
CREATE INDEX notification_delivery_due
  ON notification_delivery(status, next_attempt_at, claim_expires_at, id);

CREATE INDEX calendar_event_source ON calendar_event(source_key);
CREATE INDEX calendar_event_recipient_period
  ON calendar_event(recipient_member_id, exam_half_year_id);
CREATE INDEX calendar_event_status ON calendar_event(status);
CREATE INDEX absence_audit_report_created
  ON absence_audit_event(absence_report_id, created_at);
