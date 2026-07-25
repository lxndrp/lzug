-- Introduce globally identified people while retaining every historic membership.
-- SQLite ALTER TABLE cannot add a non-null column to populated tables, therefore
-- the migration fills person_id atomically before the application relies on it.
BEGIN TRANSACTION;

CREATE TABLE person (
  id INTEGER PRIMARY KEY,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  email TEXT NOT NULL COLLATE NOCASE UNIQUE,
  mobile TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Do not infer identity from name or email.  A suffix keeps duplicate legacy
-- contact addresses representable until an explicit, audited correction occurs.
INSERT INTO person (id, first_name, last_name, email, mobile, created_at, updated_at)
SELECT id, first_name, last_name,
       lower(trim(email)) || CASE
         WHEN row_number() OVER (PARTITION BY lower(trim(email)) ORDER BY id) = 1 THEN ''
         ELSE '+legacy-' || id
       END,
       mobile, created_at, updated_at
FROM committee_member;

ALTER TABLE committee_member ADD COLUMN person_id INTEGER REFERENCES person(id);
UPDATE committee_member SET person_id = id;
CREATE UNIQUE INDEX committee_member_one_person_per_committee
  ON committee_member(committee_id, person_id);
CREATE INDEX committee_member_person ON committee_member(person_id);

ALTER TABLE user_account ADD COLUMN person_id INTEGER REFERENCES person(id);
UPDATE user_account
SET person_id = (SELECT person_id FROM committee_member
                 WHERE committee_member.id = user_account.committee_member_id);
CREATE UNIQUE INDEX user_account_one_person ON user_account(person_id)
  WHERE person_id IS NOT NULL;

INSERT INTO schema_migration (name) VALUES ('002_add_person_memberships.sql');
COMMIT;
