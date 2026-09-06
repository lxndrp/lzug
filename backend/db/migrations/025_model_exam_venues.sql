-- Separate reusable exam venues, rooms and contacts while preserving every legacy reference.
PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

DROP TABLE IF EXISTS temp._exam_venue_migration_guard;
CREATE TEMP TABLE _exam_venue_migration_guard (
  conflict_count INTEGER NOT NULL CHECK (conflict_count = 0)
);

INSERT INTO _exam_venue_migration_guard (conflict_count)
SELECT count(*)
FROM planning_settings
WHERE default_location_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM location WHERE location.id = planning_settings.default_location_id
  );

INSERT INTO _exam_venue_migration_guard (conflict_count)
SELECT count(*)
FROM exam_day
WHERE NOT EXISTS (
  SELECT 1 FROM location WHERE location.id = exam_day.location_id
);

INSERT INTO _exam_venue_migration_guard (conflict_count)
SELECT count(*)
FROM location
WHERE NOT EXISTS (
  SELECT 1 FROM committee WHERE committee.id = location.committee_id
);

DROP TABLE IF EXISTS temp._legacy_location_plan;
CREATE TEMP TABLE _legacy_location_plan AS
SELECT
  source.id AS legacy_location_id,
  CASE
    WHEN lzug_normalize(source.name) <> ''
      AND lzug_normalize(source.street) <> ''
      AND lzug_normalize(source.postal_code) <> ''
      AND lzug_normalize(source.city) <> ''
    THEN (
      SELECT min(candidate.id)
      FROM location AS candidate
      WHERE candidate.committee_id = source.committee_id
        AND lzug_normalize(candidate.name) = lzug_normalize(source.name)
        AND lzug_normalize(candidate.street) = lzug_normalize(source.street)
        AND lzug_normalize(candidate.postal_code) = lzug_normalize(source.postal_code)
        AND lzug_normalize(candidate.city) = lzug_normalize(source.city)
    )
    ELSE source.id
  END AS venue_id,
  CASE
    WHEN lzug_normalize(source.room) = '' THEN 'Gesamter Standort'
    ELSE trim(source.room)
  END AS room_name
FROM location AS source;

INSERT INTO _exam_venue_migration_guard (conflict_count)
SELECT count(*)
FROM (
  SELECT venue_id, lzug_normalize(room_name)
  FROM _legacy_location_plan
  GROUP BY venue_id, lzug_normalize(room_name)
  HAVING count(*) > 1
);

INSERT INTO _exam_venue_migration_guard (conflict_count)
SELECT count(*)
FROM (
  SELECT representative.committee_id, lzug_normalize(representative.name)
  FROM (
    SELECT DISTINCT venue_id FROM _legacy_location_plan
  ) AS target
  JOIN location AS representative ON representative.id = target.venue_id
  GROUP BY representative.committee_id, lzug_normalize(representative.name)
  HAVING count(*) > 1
);

CREATE TABLE exam_venue (
  id INTEGER PRIMARY KEY,
  scope TEXT NOT NULL CHECK (scope IN ('global', 'committee')),
  committee_id INTEGER REFERENCES committee(id) ON DELETE RESTRICT,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  street TEXT NOT NULL,
  postal_code TEXT NOT NULL,
  city TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT 'Deutschland',
  site_name TEXT,
  entrance TEXT,
  travel_directions TEXT,
  is_accessible INTEGER CHECK (is_accessible IN (0, 1)),
  accessibility_status TEXT NOT NULL DEFAULT 'needs_clarification'
    CHECK (accessibility_status IN ('confirmed', 'needs_clarification')),
  accessibility_notes TEXT,
  latitude REAL CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
  longitude REAL CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180),
  coordinate_status TEXT NOT NULL DEFAULT 'missing'
    CHECK (coordinate_status IN ('missing', 'confirmed', 'needs_review')),
  coordinate_source TEXT,
  is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (scope = 'global' AND committee_id IS NULL)
    OR (scope = 'committee' AND committee_id IS NOT NULL)
  ),
  CHECK (
    (accessibility_status = 'confirmed' AND is_accessible IS NOT NULL)
    OR (accessibility_status = 'needs_clarification' AND is_accessible IS NULL)
  ),
  CHECK ((latitude IS NULL) = (longitude IS NULL)),
  CHECK (
    (coordinate_status = 'missing' AND latitude IS NULL AND longitude IS NULL)
    OR (
      coordinate_status = 'confirmed'
      AND latitude IS NOT NULL
      AND longitude IS NOT NULL
      AND length(trim(coordinate_source)) > 0
    )
    OR coordinate_status = 'needs_review'
  ),
  CHECK (
    is_active = 0
    OR (
      length(trim(name)) > 0
      AND length(trim(street)) > 0
      AND length(trim(postal_code)) > 0
      AND length(trim(city)) > 0
      AND length(trim(country)) > 0
      AND accessibility_status = 'confirmed'
      AND is_accessible IS NOT NULL
    )
  )
);

CREATE UNIQUE INDEX exam_venue_global_name_unique
  ON exam_venue(normalized_name)
  WHERE scope = 'global';

CREATE UNIQUE INDEX exam_venue_committee_name_unique
  ON exam_venue(committee_id, normalized_name)
  WHERE scope = 'committee';

INSERT INTO exam_venue (
  id, scope, committee_id, name, normalized_name, street, postal_code, city,
  country, is_accessible, accessibility_status, is_active, revision,
  created_at, updated_at
)
SELECT
  plan.venue_id,
  'committee',
  representative.committee_id,
  trim(representative.name),
  lzug_normalize(representative.name),
  trim(representative.street),
  trim(representative.postal_code),
  trim(representative.city),
  'Deutschland',
  NULL,
  'needs_clarification',
  0,
  1,
  min(source.created_at),
  max(source.updated_at)
FROM _legacy_location_plan AS plan
JOIN location AS representative ON representative.id = plan.venue_id
JOIN _legacy_location_plan AS grouped ON grouped.venue_id = plan.venue_id
JOIN location AS source ON source.id = grouped.legacy_location_id
GROUP BY plan.venue_id;

CREATE TABLE exam_room (
  id INTEGER PRIMARY KEY,
  venue_id INTEGER NOT NULL REFERENCES exam_venue(id) ON DELETE RESTRICT,
  name TEXT NOT NULL CHECK (length(trim(name)) > 0),
  normalized_name TEXT NOT NULL CHECK (length(normalized_name) > 0),
  building TEXT,
  wing TEXT,
  floor TEXT,
  room_number TEXT,
  access_notes TEXT,
  capacity INTEGER CHECK (capacity IS NULL OR capacity > 0),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (venue_id, normalized_name)
);

INSERT INTO exam_room (
  id, venue_id, name, normalized_name, is_active, revision, created_at, updated_at
)
SELECT
  location.id,
  plan.venue_id,
  plan.room_name,
  lzug_normalize(plan.room_name),
  location.is_active,
  1,
  location.created_at,
  location.updated_at
FROM location
JOIN _legacy_location_plan AS plan ON plan.legacy_location_id = location.id;

CREATE TABLE exam_venue_contact (
  id INTEGER PRIMARY KEY,
  venue_id INTEGER NOT NULL REFERENCES exam_venue(id) ON DELETE RESTRICT,
  label TEXT NOT NULL CHECK (length(trim(label)) > 0),
  role TEXT,
  phone TEXT,
  email TEXT,
  availability_notes TEXT,
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    length(trim(COALESCE(phone, ''))) > 0
    OR length(trim(COALESCE(email, ''))) > 0
    OR length(trim(COALESCE(availability_notes, ''))) > 0
  )
);

CREATE TABLE exam_venue_contact_room (
  contact_id INTEGER NOT NULL REFERENCES exam_venue_contact(id) ON DELETE CASCADE,
  room_id INTEGER NOT NULL REFERENCES exam_room(id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (contact_id, room_id)
);

CREATE TABLE exam_venue_audit_event (
  id INTEGER PRIMARY KEY,
  venue_id INTEGER NOT NULL,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('venue', 'room', 'contact')),
  entity_id INTEGER NOT NULL,
  entity_revision INTEGER NOT NULL CHECK (entity_revision >= 1),
  change_type TEXT NOT NULL CHECK (
    change_type IN ('created', 'updated', 'activated', 'deactivated', 'deleted', 'migrated')
  ),
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('member', 'migration')),
  actor_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  technical_actor TEXT,
  reason TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (actor_kind = 'member' AND actor_member_id IS NOT NULL AND technical_actor IS NULL)
    OR (
      actor_kind = 'migration'
      AND actor_member_id IS NULL
      AND length(trim(technical_actor)) > 0
    )
  )
);

CREATE INDEX exam_venue_audit_history
  ON exam_venue_audit_event(venue_id, created_at, id);

CREATE TABLE exam_venue_migration_report (
  id INTEGER PRIMARY KEY,
  migration_name TEXT NOT NULL UNIQUE,
  backup_reference TEXT NOT NULL,
  backup_verified INTEGER NOT NULL CHECK (backup_verified = 1),
  source_location_count INTEGER NOT NULL CHECK (source_location_count >= 0),
  venue_count INTEGER NOT NULL CHECK (venue_count >= 0),
  room_count INTEGER NOT NULL CHECK (room_count >= 0),
  grouped_location_count INTEGER NOT NULL CHECK (grouped_location_count >= 0),
  conflict_count INTEGER NOT NULL CHECK (conflict_count = 0),
  clarification_count INTEGER NOT NULL CHECK (clarification_count >= 0),
  machine_report_json TEXT NOT NULL,
  human_report TEXT NOT NULL,
  migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE legacy_location_room_mapping (
  legacy_location_id INTEGER PRIMARY KEY,
  venue_id INTEGER NOT NULL REFERENCES exam_venue(id) ON DELETE RESTRICT,
  room_id INTEGER NOT NULL UNIQUE REFERENCES exam_room(id) ON DELETE RESTRICT,
  migration_report_id INTEGER NOT NULL
    REFERENCES exam_venue_migration_report(id) ON DELETE RESTRICT,
  migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO exam_venue_migration_report (
  migration_name, backup_reference, backup_verified, source_location_count,
  venue_count, room_count, grouped_location_count, conflict_count,
  clarification_count, machine_report_json, human_report, migrated_at
)
SELECT
  '025_model_exam_venues.sql',
  lzug_migration_backup(),
  1,
  (SELECT count(*) FROM location),
  (SELECT count(*) FROM exam_venue),
  (SELECT count(*) FROM exam_room),
  (SELECT count(*) FROM location) - (SELECT count(*) FROM exam_venue),
  0,
  (SELECT count(*) FROM exam_venue),
  lzug_migration_report_json(),
  lzug_migration_report_text(),
  lzug_migration_timestamp();

INSERT INTO legacy_location_room_mapping (
  legacy_location_id, venue_id, room_id, migration_report_id
)
SELECT
  plan.legacy_location_id,
  plan.venue_id,
  plan.legacy_location_id,
  (SELECT id FROM exam_venue_migration_report WHERE migration_name = '025_model_exam_venues.sql')
FROM _legacy_location_plan AS plan;

INSERT INTO exam_venue_audit_event (
  venue_id, entity_type, entity_id, entity_revision, change_type,
  actor_kind, technical_actor, details_json
)
SELECT
  venue.id,
  'venue',
  venue.id,
  venue.revision,
  'migrated',
  'migration',
  '025_model_exam_venues.sql',
  json_object(
    'legacy_location_ids',
    json((
      SELECT json_group_array(mapping.legacy_location_id)
      FROM legacy_location_room_mapping AS mapping
      WHERE mapping.venue_id = venue.id
      ORDER BY mapping.legacy_location_id
    )),
    'accessibility_status',
    venue.accessibility_status
  )
FROM exam_venue AS venue;

INSERT INTO exam_venue_audit_event (
  venue_id, entity_type, entity_id, entity_revision, change_type,
  actor_kind, technical_actor, details_json
)
SELECT
  room.venue_id,
  'room',
  room.id,
  room.revision,
  'migrated',
  'migration',
  '025_model_exam_venues.sql',
  json_object(
    'legacy_location_id', room.id,
    'legacy_room_name', room.name
  )
FROM exam_room AS room;

CREATE TABLE planning_settings_025 (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL UNIQUE REFERENCES exam_round(id) ON DELETE CASCADE,
  calendar_week_from TEXT NOT NULL,
  calendar_week_to TEXT NOT NULL,
  exams_per_day INTEGER NOT NULL CHECK (exams_per_day >= 1),
  max_exam_days_per_week INTEGER NOT NULL DEFAULT 3
    CHECK (max_exam_days_per_week BETWEEN 1 AND 5),
  lunch_break_enabled INTEGER NOT NULL DEFAULT 1 CHECK (lunch_break_enabled IN (0, 1)),
  exclude_public_holidays INTEGER NOT NULL DEFAULT 0
    CHECK (exclude_public_holidays IN (0, 1)),
  holiday_subdivision_code TEXT,
  default_room_id INTEGER REFERENCES exam_room(id) ON DELETE SET NULL,
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

INSERT INTO planning_settings_025 (
  id, exam_round_id, calendar_week_from, calendar_week_to, exams_per_day,
  max_exam_days_per_week, lunch_break_enabled, exclude_public_holidays,
  holiday_subdivision_code, default_room_id, updated_by_member_id,
  created_at, updated_at
)
SELECT
  settings.id,
  settings.exam_round_id,
  settings.calendar_week_from,
  settings.calendar_week_to,
  settings.exams_per_day,
  settings.max_exam_days_per_week,
  settings.lunch_break_enabled,
  settings.exclude_public_holidays,
  settings.holiday_subdivision_code,
  mapping.room_id,
  settings.updated_by_member_id,
  settings.created_at,
  settings.updated_at
FROM planning_settings AS settings
LEFT JOIN legacy_location_room_mapping AS mapping
  ON mapping.legacy_location_id = settings.default_location_id;

DROP TABLE planning_settings;
ALTER TABLE planning_settings_025 RENAME TO planning_settings;

CREATE TABLE exam_day_025 (
  id INTEGER PRIMARY KEY,
  exam_round_id INTEGER NOT NULL REFERENCES exam_round(id) ON DELETE CASCADE,
  room_id INTEGER NOT NULL REFERENCES exam_room(id) ON DELETE RESTRICT,
  date TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'proposed' CHECK (
    status IN ('proposed', 'confirmed', 'changed', 'cancelled', 'completed')
  ),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  closure_status TEXT NOT NULL DEFAULT 'open' CHECK (
    closure_status IN ('open', 'closed', 'closed_exception', 'reopening', 'historical')
  ),
  lunch_break_enabled INTEGER NOT NULL DEFAULT 1 CHECK (lunch_break_enabled IN (0, 1)),
  created_from_proposal INTEGER NOT NULL DEFAULT 1 CHECK (created_from_proposal IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (exam_round_id, date)
);

INSERT INTO exam_day_025 (
  id, exam_round_id, room_id, date, status, revision, closure_status,
  lunch_break_enabled, created_from_proposal, created_at, updated_at
)
SELECT
  day.id,
  day.exam_round_id,
  mapping.room_id,
  day.date,
  day.status,
  day.revision,
  day.closure_status,
  day.lunch_break_enabled,
  day.created_from_proposal,
  day.created_at,
  day.updated_at
FROM exam_day AS day
JOIN legacy_location_room_mapping AS mapping
  ON mapping.legacy_location_id = day.location_id;

DROP TABLE exam_day;
ALTER TABLE exam_day_025 RENAME TO exam_day;
CREATE INDEX exam_day_round_date ON exam_day(exam_round_id, date);

UPDATE confirmed_plan_revision
SET before_state_json = lzug_migrate_plan_json(before_state_json),
    after_state_json = lzug_migrate_plan_json(after_state_json);

DROP TABLE location;

CREATE TRIGGER exam_venue_active_requires_room_insert
BEFORE INSERT ON exam_venue
WHEN NEW.is_active = 1
BEGIN
  SELECT RAISE(ABORT, 'active exam venue needs an active room');
END;

CREATE TRIGGER exam_venue_active_requires_room_update
BEFORE UPDATE OF is_active, name, street, postal_code, city, country,
  accessibility_status, is_accessible ON exam_venue
WHEN NEW.is_active = 1 AND NOT EXISTS (
  SELECT 1 FROM exam_room WHERE exam_room.venue_id = NEW.id AND exam_room.is_active = 1
)
BEGIN
  SELECT RAISE(ABORT, 'active exam venue needs an active room');
END;

CREATE TRIGGER exam_room_keep_active_venue_on_update
BEFORE UPDATE OF is_active, venue_id ON exam_room
WHEN EXISTS (
  SELECT 1 FROM exam_venue WHERE exam_venue.id = OLD.venue_id AND exam_venue.is_active = 1
)
AND NOT EXISTS (
  SELECT 1 FROM exam_room
  WHERE exam_room.venue_id = OLD.venue_id
    AND exam_room.id <> OLD.id
    AND exam_room.is_active = 1
)
AND (NEW.is_active = 0 OR NEW.venue_id <> OLD.venue_id)
BEGIN
  SELECT RAISE(ABORT, 'active exam venue needs an active room');
END;

CREATE TRIGGER exam_room_keep_active_venue_on_delete
BEFORE DELETE ON exam_room
WHEN EXISTS (
  SELECT 1 FROM exam_venue WHERE exam_venue.id = OLD.venue_id AND exam_venue.is_active = 1
)
AND NOT EXISTS (
  SELECT 1 FROM exam_room
  WHERE exam_room.venue_id = OLD.venue_id
    AND exam_room.id <> OLD.id
    AND exam_room.is_active = 1
)
BEGIN
  SELECT RAISE(ABORT, 'active exam venue needs an active room');
END;

CREATE TRIGGER exam_venue_contact_room_same_venue_insert
BEFORE INSERT ON exam_venue_contact_room
WHEN (
  SELECT venue_id FROM exam_venue_contact WHERE id = NEW.contact_id
) <> (
  SELECT venue_id FROM exam_room WHERE id = NEW.room_id
)
BEGIN
  SELECT RAISE(ABORT, 'contact room must belong to the same exam venue');
END;

CREATE TRIGGER exam_venue_contact_room_same_venue_update
BEFORE UPDATE ON exam_venue_contact_room
WHEN (
  SELECT venue_id FROM exam_venue_contact WHERE id = NEW.contact_id
) <> (
  SELECT venue_id FROM exam_room WHERE id = NEW.room_id
)
BEGIN
  SELECT RAISE(ABORT, 'contact room must belong to the same exam venue');
END;

CREATE TRIGGER exam_venue_audit_immutable_update
BEFORE UPDATE ON exam_venue_audit_event
BEGIN
  SELECT RAISE(ABORT, 'exam venue audit is immutable');
END;

CREATE TRIGGER exam_venue_audit_immutable_delete
BEFORE DELETE ON exam_venue_audit_event
BEGIN
  SELECT RAISE(ABORT, 'exam venue audit is immutable');
END;

CREATE TRIGGER exam_venue_migration_report_immutable_update
BEFORE UPDATE ON exam_venue_migration_report
BEGIN
  SELECT RAISE(ABORT, 'exam venue migration report is immutable');
END;

CREATE TRIGGER exam_venue_migration_report_immutable_delete
BEFORE DELETE ON exam_venue_migration_report
BEGIN
  SELECT RAISE(ABORT, 'exam venue migration report is immutable');
END;

INSERT INTO _exam_venue_migration_guard (conflict_count)
SELECT count(*) FROM pragma_foreign_key_check;

DROP TABLE _exam_venue_migration_guard;
DROP TABLE _legacy_location_plan;

INSERT INTO schema_migration (name) VALUES ('025_model_exam_venues.sql');
COMMIT;
PRAGMA foreign_keys = ON;
