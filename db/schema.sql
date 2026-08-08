-- lzug relationales Basisschema
-- Stand: 2026-06-24
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
       ('005_add_exam_day_attendance.sql');

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
  password_hash TEXT NOT NULL,
  passkey_enabled INTEGER NOT NULL DEFAULT 0 CHECK (passkey_enabled IN (0, 1)),
  two_factor_enabled INTEGER NOT NULL DEFAULT 0 CHECK (two_factor_enabled IN (0, 1)),
  last_login_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (two_factor_enabled = 0 OR passkey_enabled = 1)
);

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
      'resolved'
    )
  ),
  selected_replacement_member_id INTEGER REFERENCES committee_member(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE replacement_response (
  id INTEGER PRIMARY KEY,
  absence_report_id INTEGER NOT NULL REFERENCES absence_report(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE CASCADE,
  response TEXT NOT NULL DEFAULT 'pending' CHECK (response IN ('pending', 'available', 'unavailable')),
  responded_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (absence_report_id, committee_member_id),
  CHECK (response = 'pending' OR responded_at IS NOT NULL)
);

CREATE TABLE notification (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER REFERENCES exam_round(id) ON DELETE CASCADE,
  recipient_member_id INTEGER REFERENCES committee_member(id) ON DELETE SET NULL,
  recipient_email TEXT NOT NULL,
  notification_type TEXT NOT NULL CHECK (
    notification_type IN (
      'exam_round_created',
      'availability_requested',
      'availability_reminder',
      'availability_deadline_missed',
      'plan_confirmed',
      'plan_changed',
      'examiner_absence_reported',
      'fallback_confirmation_requested',
      'fallback_confirmation_expired',
      'replacement_requested',
      'urgent_replacement_requested',
      'exam_day_cancelled_ihk_notice'
    )
  ),
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'scheduled', 'sent', 'failed', 'cancelled')),
  scheduled_at TEXT,
  sent_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE calendar_event (
  id INTEGER PRIMARY KEY,
  exam_slot_id INTEGER REFERENCES exam_slot(id) ON DELETE CASCADE,
  exam_day_id INTEGER REFERENCES exam_day(id) ON DELETE CASCADE,
  recipient_member_id INTEGER REFERENCES committee_member(id) ON DELETE SET NULL,
  external_event_id TEXT,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'updated', 'cancelled')),
  sent_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (exam_slot_id IS NOT NULL OR exam_day_id IS NOT NULL)
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

CREATE INDEX notification_status_scheduled
  ON notification(status, scheduled_at);

CREATE INDEX calendar_event_status
  ON calendar_event(status);
