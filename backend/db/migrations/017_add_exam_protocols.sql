-- Add immutable, jointly confirmed protocols for exams that actually started.
BEGIN TRANSACTION;

CREATE TABLE exam_protocol (
  id INTEGER PRIMARY KEY,
  exam_slot_id INTEGER NOT NULL UNIQUE REFERENCES exam_slot(id) ON DELETE CASCADE,
  current_version INTEGER NOT NULL DEFAULT 1 CHECK (current_version >= 1),
  created_by_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  source TEXT NOT NULL DEFAULT 'application' CHECK (source IN ('application', 'migration')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exam_protocol_participant (
  id INTEGER PRIMARY KEY,
  exam_protocol_id INTEGER NOT NULL REFERENCES exam_protocol(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_protocol_id, committee_member_id)
);

CREATE TABLE exam_protocol_correction_request (
  id INTEGER PRIMARY KEY,
  exam_protocol_id INTEGER NOT NULL REFERENCES exam_protocol(id) ON DELETE CASCADE,
  exam_protocol_revision_id INTEGER NOT NULL
    REFERENCES exam_protocol_revision(id) ON DELETE RESTRICT,
  requested_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'opened')),
  requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  opened_by_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  opened_at TEXT,
  reopening_reference TEXT
);

CREATE TABLE exam_protocol_revision (
  id INTEGER PRIMARY KEY,
  exam_protocol_id INTEGER NOT NULL REFERENCES exam_protocol(id) ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version >= 1),
  declaration TEXT CHECK (
    declaration IS NULL
    OR declaration IN ('without_special_occurrences', 'with_special_occurrences')
  ),
  workflow_state TEXT NOT NULL DEFAULT 'draft' CHECK (
    workflow_state IN ('draft', 'submitted', 'correction_open')
  ),
  previous_revision_id INTEGER REFERENCES exam_protocol_revision(id) ON DELETE RESTRICT,
  correction_request_id INTEGER REFERENCES exam_protocol_correction_request(id) ON DELETE RESTRICT,
  changed_by_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  change_reason TEXT,
  submitted_by_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  submitted_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_protocol_id, version)
);

CREATE TABLE exam_protocol_entry (
  id INTEGER PRIMARY KEY,
  exam_protocol_revision_id INTEGER NOT NULL REFERENCES exam_protocol_revision(id) ON DELETE CASCADE,
  category TEXT NOT NULL CHECK (category IN (
    'late_start', 'interruption', 'termination', 'different_staffing',
    'procedural_deviation', 'objection_or_reservation', 'other'
  )),
  statement TEXT NOT NULL CHECK (length(trim(statement)) > 0),
  occurred_from TEXT NOT NULL CHECK (length(trim(occurred_from)) > 0),
  occurred_to TEXT,
  recorded_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (occurred_to IS NULL OR occurred_to >= occurred_from)
);

CREATE TABLE exam_protocol_response (
  id INTEGER PRIMARY KEY,
  exam_protocol_revision_id INTEGER NOT NULL REFERENCES exam_protocol_revision(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  response TEXT NOT NULL CHECK (response IN ('confirmed', 'reservation')),
  exam_protocol_entry_id INTEGER REFERENCES exam_protocol_entry(id) ON DELETE RESTRICT,
  statement TEXT,
  responded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_protocol_revision_id, committee_member_id),
  CHECK (
    (response = 'confirmed' AND exam_protocol_entry_id IS NULL AND statement IS NULL)
    OR (
      response = 'reservation'
      AND length(trim(statement)) > 0
    )
  )
);

CREATE TABLE exam_protocol_retention (
  id INTEGER PRIMARY KEY,
  exam_protocol_id INTEGER NOT NULL UNIQUE REFERENCES exam_protocol(id) ON DELETE CASCADE,
  rule_reference TEXT NOT NULL CHECK (length(trim(rule_reference)) > 0),
  retain_until TEXT,
  legal_hold INTEGER NOT NULL DEFAULT 0 CHECK (legal_hold IN (0, 1)),
  hold_reason TEXT,
  updated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (legal_hold = 0 OR length(trim(hold_reason)) > 0)
);

CREATE INDEX exam_protocol_slot ON exam_protocol(exam_slot_id);
CREATE INDEX exam_protocol_participant_member
  ON exam_protocol_participant(committee_member_id, exam_protocol_id);
CREATE INDEX exam_protocol_revision_protocol
  ON exam_protocol_revision(exam_protocol_id, version);
CREATE INDEX exam_protocol_entry_revision
  ON exam_protocol_entry(exam_protocol_revision_id, id);
CREATE INDEX exam_protocol_response_revision
  ON exam_protocol_response(exam_protocol_revision_id, committee_member_id);
CREATE INDEX exam_protocol_correction_protocol_status
  ON exam_protocol_correction_request(exam_protocol_id, status);

-- Only exams that are still operationally open after a recorded start become
-- protocol-required during an upgrade. Historical completed slots deliberately
-- remain without an invented protocol or no-occurrence declaration.
INSERT INTO exam_protocol (exam_slot_id, current_version, source, created_at, updated_at)
SELECT id, 1, 'migration', actual_started_at, CURRENT_TIMESTAMP
FROM exam_slot
WHERE actual_started_at IS NOT NULL
  AND execution_status IN ('running', 'needs_follow_up');

INSERT INTO exam_protocol_revision (
  exam_protocol_id, version, declaration, workflow_state, change_reason, created_at
)
SELECT id, 1, NULL, 'draft', 'upgrade_of_started_exam', created_at
FROM exam_protocol
WHERE source = 'migration';

INSERT INTO exam_protocol_participant (exam_protocol_id, committee_member_id, created_at)
SELECT DISTINCT protocol.id, assignment.committee_member_id, protocol.created_at
FROM exam_protocol AS protocol
JOIN exam_slot AS slot ON slot.id = protocol.exam_slot_id
JOIN exam_day_assignment AS assignment ON assignment.exam_day_id = slot.exam_day_id
JOIN member_exam_attendance AS attendance
  ON attendance.exam_day_id = slot.exam_day_id
 AND attendance.committee_member_id = assignment.committee_member_id
WHERE protocol.source = 'migration'
  AND assignment.assignment_role = 'examiner'
  AND attendance.status IN ('present', 'late')
  AND (
    assignment.day_part = 'full_day'
    OR (assignment.day_part = 'morning' AND CAST(substr(slot.starts_at, 12, 2) AS INTEGER) < 12)
    OR (assignment.day_part = 'afternoon' AND CAST(substr(slot.starts_at, 12, 2) AS INTEGER) >= 12)
  );

INSERT INTO schema_migration (name) VALUES ('017_add_exam_protocols.sql');
COMMIT;
