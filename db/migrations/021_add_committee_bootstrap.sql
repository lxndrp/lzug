-- Add the operator-only committee lifecycle and immutable administrative evidence.
BEGIN TRANSACTION;

ALTER TABLE committee ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
  CHECK (is_active IN (0, 1));
ALTER TABLE committee ADD COLUMN bootstrap_state TEXT NOT NULL DEFAULT 'needs_clarification'
  CHECK (bootstrap_state IN ('ready', 'needs_clarification', 'conflict'));

UPDATE committee
SET bootstrap_state = CASE
  WHEN (
    SELECT count(*)
    FROM committee_member
    WHERE committee_member.committee_id = committee.id
      AND committee_member.committee_role = 'chair'
      AND committee_member.is_active = 1
  ) = 1 THEN 'ready'
  WHEN (
    SELECT count(*)
    FROM committee_member
    WHERE committee_member.committee_id = committee.id
      AND committee_member.committee_role = 'chair'
      AND committee_member.is_active = 1
  ) = 0 THEN 'needs_clarification'
  ELSE 'conflict'
END;

CREATE TABLE committee_admin_operation (
  id INTEGER PRIMARY KEY,
  operation_type TEXT NOT NULL CHECK (
    operation_type IN (
      'bootstrap', 'complete', 'reinvite', 'deactivate', 'reactivate',
      'legacy_assessment'
    )
  ),
  committee_id INTEGER NOT NULL REFERENCES committee(id) ON DELETE RESTRICT,
  person_ids_json TEXT NOT NULL,
  membership_ids_json TEXT NOT NULL,
  account_ids_json TEXT NOT NULL,
  result TEXT NOT NULL CHECK (
    result IN ('succeeded', 'ready', 'needs_clarification', 'conflict')
  ),
  occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  technical_source TEXT NOT NULL CHECK (technical_source IN ('operator-cli', 'migration')),
  idempotency_key TEXT UNIQUE,
  request_hash TEXT CHECK (request_hash IS NULL OR length(request_hash) = 64),
  reason TEXT,
  response_json TEXT,
  CHECK (
    (technical_source = 'operator-cli'
      AND idempotency_key IS NOT NULL
      AND request_hash IS NOT NULL
      AND response_json IS NOT NULL)
    OR
    (technical_source = 'migration'
      AND idempotency_key IS NULL
      AND request_hash IS NULL
      AND response_json IS NULL)
  ),
  CHECK (
    operation_type NOT IN ('deactivate', 'reactivate')
    OR length(trim(reason)) > 0
  )
);

CREATE INDEX committee_admin_operation_committee
  ON committee_admin_operation(committee_id, occurred_at);

INSERT INTO committee_admin_operation (
  operation_type, committee_id, person_ids_json, membership_ids_json,
  account_ids_json, result, technical_source
)
SELECT
  'legacy_assessment',
  committee.id,
  '[' || COALESCE((
    SELECT group_concat(committee_member.person_id, ',')
    FROM committee_member
    WHERE committee_member.committee_id = committee.id
  ), '') || ']',
  '[' || COALESCE((
    SELECT group_concat(committee_member.id, ',')
    FROM committee_member
    WHERE committee_member.committee_id = committee.id
  ), '') || ']',
  '[' || COALESCE((
    SELECT group_concat(user_account.id, ',')
    FROM user_account
    WHERE user_account.person_id IN (
      SELECT committee_member.person_id
      FROM committee_member
      WHERE committee_member.committee_id = committee.id
    )
  ), '') || ']',
  committee.bootstrap_state,
  'migration'
FROM committee;

CREATE TRIGGER committee_admin_operation_immutable_update
BEFORE UPDATE ON committee_admin_operation
BEGIN
  SELECT RAISE(ABORT, 'committee admin evidence is immutable');
END;

CREATE TRIGGER committee_admin_operation_immutable_delete
BEFORE DELETE ON committee_admin_operation
BEGIN
  SELECT RAISE(ABORT, 'committee admin evidence is immutable');
END;

INSERT INTO schema_migration (name) VALUES ('021_add_committee_bootstrap.sql');
COMMIT;
