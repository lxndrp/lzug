-- Persist the public age backup recipient and its secret-free audit trail.
BEGIN TRANSACTION;

CREATE TABLE backup_recipient (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  recipient TEXT NOT NULL UNIQUE CHECK (recipient LIKE 'age1%'),
  fingerprint TEXT NOT NULL CHECK (
    fingerprint GLOB 'sha256:[0-9a-f]*' AND length(fingerprint) = 71
  ),
  activated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE backup_recipient_audit (
  id INTEGER PRIMARY KEY,
  action TEXT NOT NULL CHECK (action IN ('set', 'replace', 'migrate')),
  previous_fingerprint TEXT,
  fingerprint TEXT NOT NULL CHECK (
    fingerprint GLOB 'sha256:[0-9a-f]*' AND length(fingerprint) = 71
  ),
  technical_actor TEXT NOT NULL DEFAULT 'operator-cli'
    CHECK (technical_actor = 'operator-cli'),
  occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX backup_recipient_audit_occurred
  ON backup_recipient_audit(occurred_at DESC, id DESC);

INSERT INTO schema_migration (name) VALUES ('026_add_backup_recipient.sql');
COMMIT;
