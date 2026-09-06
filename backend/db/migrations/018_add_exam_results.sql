-- Add version-bound assessments and immutable result histories.
BEGIN TRANSACTION;

ALTER TABLE committee
  ADD COLUMN ihk TEXT NOT NULL DEFAULT 'Nicht konfiguriert'
  CHECK (length(trim(ihk)) > 0);

CREATE TABLE assessment_model_version (
  id INTEGER PRIMARY KEY,
  model_key TEXT NOT NULL CHECK (length(trim(model_key)) > 0),
  version INTEGER NOT NULL CHECK (version >= 1),
  ihk TEXT NOT NULL CHECK (length(trim(ihk)) > 0),
  occupation TEXT NOT NULL CHECK (length(trim(occupation)) > 0),
  specialization TEXT,
  training_regulation TEXT NOT NULL CHECK (length(trim(training_regulation)) > 0),
  exam_regulation TEXT NOT NULL CHECK (length(trim(exam_regulation)) > 0),
  ihk_guidelines TEXT NOT NULL CHECK (length(trim(ihk_guidelines)) > 0),
  valid_from TEXT NOT NULL,
  valid_until TEXT,
  official_scale_min TEXT NOT NULL DEFAULT '0' CHECK (CAST(official_scale_min AS REAL) = 0),
  official_scale_max TEXT NOT NULL DEFAULT '100' CHECK (CAST(official_scale_max AS REAL) = 100),
  rules_json TEXT NOT NULL CHECK (length(trim(rules_json)) > 0),
  retention_rule_reference TEXT NOT NULL CHECK (length(trim(retention_rule_reference)) > 0),
  retention_years INTEGER NOT NULL DEFAULT 15 CHECK (retention_years >= 15),
  created_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (model_key, version),
  CHECK (valid_until IS NULL OR valid_until >= valid_from)
);

CREATE TABLE exam_round_assessment_binding (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL UNIQUE REFERENCES exam_round(id) ON DELETE CASCADE,
  assessment_model_version_id INTEGER NOT NULL
    REFERENCES assessment_model_version(id) ON DELETE RESTRICT,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  bound_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  binding_reason TEXT NOT NULL CHECK (length(trim(binding_reason)) > 0),
  bound_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exam_result (
  id INTEGER PRIMARY KEY,
  round_candidate_id INTEGER NOT NULL UNIQUE REFERENCES round_candidate(id) ON DELETE CASCADE,
  current_state TEXT NOT NULL DEFAULT 'incomplete' CHECK (
    current_state IN ('incomplete', 'calculation_ready', 'determined', 'communicated')
  ),
  correction_open INTEGER NOT NULL DEFAULT 0 CHECK (correction_open IN (0, 1)),
  version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
  source TEXT NOT NULL DEFAULT 'application' CHECK (source IN ('application', 'migration')),
  legacy_status TEXT CHECK (legacy_status IS NULL OR legacy_status = 'no_result_data_in_lzug'),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE individual_assessment (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  component_key TEXT NOT NULL CHECK (length(trim(component_key)) > 0),
  criterion_key TEXT NOT NULL CHECK (length(trim(criterion_key)) > 0),
  assessor_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  revision INTEGER NOT NULL CHECK (revision >= 1),
  raw_points TEXT NOT NULL,
  normalized_points TEXT NOT NULL CHECK (
    CAST(normalized_points AS REAL) >= 0 AND CAST(normalized_points AS REAL) <= 100
  ),
  rationale TEXT,
  status TEXT NOT NULL CHECK (status IN ('draft', 'submitted', 'withdrawn', 'superseded')),
  previous_assessment_id INTEGER REFERENCES individual_assessment(id) ON DELETE RESTRICT,
  change_reason TEXT,
  submitted_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_result_id, component_key, criterion_key, assessor_member_id, revision),
  CHECK (status != 'submitted' OR submitted_at IS NOT NULL)
);

CREATE TABLE assessment_disclosure (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  component_key TEXT NOT NULL CHECK (length(trim(component_key)) > 0),
  disclosed_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  disclosed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_result_id, component_key)
);

CREATE TABLE committee_assessment (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  component_key TEXT NOT NULL CHECK (length(trim(component_key)) > 0),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  points TEXT NOT NULL CHECK (CAST(points AS REAL) >= 0 AND CAST(points AS REAL) <= 100),
  rationale TEXT,
  participant_member_ids_json TEXT NOT NULL,
  vote_json TEXT NOT NULL,
  dissent_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded')),
  previous_assessment_id INTEGER REFERENCES committee_assessment(id) ON DELETE RESTRICT,
  determined_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  determined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_result_id, component_key, revision)
);

CREATE TABLE external_exam_result (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  area_key TEXT NOT NULL CHECK (length(trim(area_key)) > 0),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  points TEXT NOT NULL CHECK (CAST(points AS REAL) >= 0 AND CAST(points AS REAL) <= 100),
  grade TEXT,
  professional_status TEXT NOT NULL CHECK (length(trim(professional_status)) > 0),
  determining_authority TEXT NOT NULL CHECK (length(trim(determining_authority)) > 0),
  source_reference TEXT NOT NULL CHECK (length(trim(source_reference)) > 0),
  status TEXT NOT NULL DEFAULT 'unconfirmed' CHECK (
    status IN ('unconfirmed', 'confirmed', 'replaced')
  ),
  recorded_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  confirmed_by_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  confirmed_at TEXT,
  previous_external_result_id INTEGER REFERENCES external_exam_result(id) ON DELETE RESTRICT,
  correction_reason TEXT,
  UNIQUE (exam_result_id, area_key, revision),
  CHECK (
    (status = 'confirmed' AND confirmed_by_member_id IS NOT NULL AND confirmed_at IS NOT NULL)
    OR status != 'confirmed'
  ),
  CHECK (confirmed_by_member_id IS NULL OR confirmed_by_member_id != recorded_by_member_id)
);

CREATE TABLE result_calculation (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  version INTEGER NOT NULL CHECK (version >= 1),
  input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint) = 64),
  total_points TEXT NOT NULL CHECK (
    CAST(total_points AS REAL) >= 0 AND CAST(total_points AS REAL) <= 100
  ),
  grade TEXT NOT NULL CHECK (length(trim(grade)) > 0),
  passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
  calculation_path_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_result_id, version),
  UNIQUE (exam_result_id, input_fingerprint)
);

CREATE TABLE result_determination (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  revision INTEGER NOT NULL CHECK (revision >= 1),
  result_calculation_id INTEGER NOT NULL REFERENCES result_calculation(id) ON DELETE RESTRICT,
  participant_member_ids_json TEXT NOT NULL,
  vote_json TEXT NOT NULL,
  dissent_json TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'superseded')),
  previous_determination_id INTEGER REFERENCES result_determination(id) ON DELETE RESTRICT,
  correction_id INTEGER REFERENCES result_correction(id) ON DELETE RESTRICT,
  determined_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  determined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_result_id, revision)
);

CREATE TABLE result_record_confirmation (
  id INTEGER PRIMARY KEY,
  result_determination_id INTEGER NOT NULL
    REFERENCES result_determination(id) ON DELETE CASCADE,
  committee_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  confirmed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (result_determination_id, committee_member_id)
);

CREATE TABLE result_correction (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  result_determination_id INTEGER NOT NULL
    REFERENCES result_determination(id) ON DELETE RESTRICT,
  reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
  requested_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'completed')),
  reopening_reference TEXT,
  requested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);

CREATE TABLE result_communication (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  result_determination_id INTEGER NOT NULL
    REFERENCES result_determination(id) ON DELETE RESTRICT,
  method TEXT NOT NULL CHECK (length(trim(method)) > 0),
  responsible_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  communicated_at TEXT NOT NULL,
  external_document_status TEXT,
  external_document_reference TEXT,
  status TEXT NOT NULL DEFAULT 'current' CHECK (status IN ('current', 'obsolete')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE result_retention (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL UNIQUE REFERENCES exam_result(id) ON DELETE CASCADE,
  rule_reference TEXT NOT NULL CHECK (length(trim(rule_reference)) > 0),
  period_start TEXT,
  retain_until TEXT,
  legal_hold INTEGER NOT NULL DEFAULT 0 CHECK (legal_hold IN (0, 1)),
  hold_reason TEXT,
  updated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (retain_until IS NULL OR period_start IS NOT NULL),
  CHECK (retain_until IS NULL OR retain_until >= period_start),
  CHECK (legal_hold = 0 OR length(trim(hold_reason)) > 0)
);

CREATE TABLE result_export (
  id INTEGER PRIMARY KEY,
  exam_result_id INTEGER NOT NULL REFERENCES exam_result(id) ON DELETE CASCADE,
  result_determination_id INTEGER REFERENCES result_determination(id) ON DELETE RESTRICT,
  export_kind TEXT NOT NULL CHECK (export_kind IN ('machine', 'human')),
  status TEXT NOT NULL CHECK (status IN ('draft', 'determined', 'superseded')),
  generated_by_member_id INTEGER NOT NULL REFERENCES committee_member(id) ON DELETE RESTRICT,
  generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX assessment_model_applicability
  ON assessment_model_version(ihk, occupation, specialization, valid_from, valid_until);
CREATE INDEX individual_assessment_current
  ON individual_assessment(exam_result_id, component_key, assessor_member_id, status);
CREATE INDEX committee_assessment_current
  ON committee_assessment(exam_result_id, component_key, status);
CREATE INDEX external_exam_result_current
  ON external_exam_result(exam_result_id, area_key, status);
CREATE INDEX result_calculation_result ON result_calculation(exam_result_id, version);
CREATE INDEX result_determination_current
  ON result_determination(exam_result_id, status);
CREATE INDEX result_correction_status ON result_correction(exam_result_id, status);
CREATE INDEX result_communication_status
  ON result_communication(exam_result_id, status);
CREATE INDEX result_export_result ON result_export(exam_result_id, generated_at);

-- Completed historical slots are marked explicitly without inventing a model,
-- assessment, calculation, or determination. Planned and running cases remain
-- bindable through the normal explicit workflow.
INSERT INTO exam_result (round_candidate_id, source, legacy_status, created_at, updated_at)
SELECT DISTINCT slot.round_candidate_id, 'migration', 'no_result_data_in_lzug',
       COALESCE(slot.actual_completed_at, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP
FROM exam_slot AS slot
WHERE slot.execution_status = 'completed';

INSERT INTO schema_migration (name) VALUES ('018_add_exam_results.sql');
COMMIT;
