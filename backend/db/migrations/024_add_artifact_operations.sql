-- Add stable instance identity and secret-free backup/export operation evidence.
BEGIN TRANSACTION;

CREATE TABLE instance_metadata (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  instance_id TEXT NOT NULL UNIQUE CHECK (length(instance_id) = 36),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO instance_metadata (id, instance_id)
VALUES (
  1,
  lower(
    substr(hex(randomblob(16)), 1, 8) || '-' ||
    substr(hex(randomblob(16)), 1, 4) || '-4' ||
    substr(hex(randomblob(16)), 2, 3) || '-a' ||
    substr(hex(randomblob(16)), 2, 3) || '-' ||
    substr(hex(randomblob(16)), 1, 12)
  )
);

CREATE TABLE artifact_operation (
  id INTEGER PRIMARY KEY,
  operation_type TEXT NOT NULL CHECK (operation_type IN (
    'backup', 'restore', 'full_export'
  )),
  artifact_id TEXT,
  artifact_type TEXT CHECK (artifact_type IN ('backup', 'full_export')),
  snapshot_at TEXT,
  recipient_key_fingerprint TEXT,
  result TEXT NOT NULL CHECK (result IN ('succeeded', 'failed')),
  error_code TEXT,
  technical_actor TEXT NOT NULL DEFAULT 'operator-cli'
    CHECK (technical_actor = 'operator-cli'),
  occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (
    (result = 'succeeded' AND artifact_id IS NOT NULL AND error_code IS NULL)
    OR (result = 'failed' AND error_code IS NOT NULL)
  )
);

CREATE INDEX artifact_operation_occurred
  ON artifact_operation(operation_type, occurred_at DESC, id DESC);

INSERT INTO schema_migration (name) VALUES ('024_add_artifact_operations.sql');
COMMIT;
