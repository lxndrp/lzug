PRAGMA foreign_keys = OFF;
BEGIN TRANSACTION;

ALTER TABLE exam_venue_audit_event RENAME TO exam_venue_audit_event_025;

CREATE TABLE exam_venue_audit_event (
  id INTEGER PRIMARY KEY,
  venue_id INTEGER NOT NULL,
  entity_type TEXT NOT NULL CHECK (entity_type IN ('venue', 'room', 'contact')),
  entity_id INTEGER NOT NULL,
  entity_revision INTEGER NOT NULL CHECK (entity_revision >= 1),
  change_type TEXT NOT NULL CHECK (
    change_type IN (
      'created', 'updated', 'activated', 'deactivated', 'deleted', 'migrated',
      'promotion_requested', 'promotion_approved', 'promotion_rejected'
    )
  ),
  actor_kind TEXT NOT NULL CHECK (actor_kind IN ('member', 'operator', 'migration')),
  actor_member_id INTEGER REFERENCES committee_member(id) ON DELETE RESTRICT,
  technical_actor TEXT,
  reason TEXT,
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (actor_kind = 'member' AND actor_member_id IS NOT NULL AND technical_actor IS NULL)
    OR (
      actor_kind IN ('operator', 'migration')
      AND actor_member_id IS NULL
      AND length(trim(technical_actor)) > 0
    )
  )
);

INSERT INTO exam_venue_audit_event (
  id, venue_id, entity_type, entity_id, entity_revision, change_type,
  actor_kind, actor_member_id, technical_actor, reason, details_json, created_at
)
SELECT
  id, venue_id, entity_type, entity_id, entity_revision, change_type,
  actor_kind, actor_member_id, technical_actor, reason, details_json, created_at
FROM exam_venue_audit_event_025;

DROP TABLE exam_venue_audit_event_025;

CREATE INDEX exam_venue_audit_history
  ON exam_venue_audit_event(venue_id, created_at, id);

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

INSERT INTO schema_migration (name)
VALUES ('027_expand_exam_venue_audit.sql');

COMMIT;
PRAGMA foreign_keys = ON;
