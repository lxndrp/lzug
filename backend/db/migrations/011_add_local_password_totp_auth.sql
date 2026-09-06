-- Add local password, TOTP, and one-time recovery-code state for #266.
BEGIN TRANSACTION;

ALTER TABLE user_account ADD COLUMN totp_secret_encrypted TEXT;
ALTER TABLE user_account ADD COLUMN totp_last_step INTEGER;
ALTER TABLE user_account ADD COLUMN totp_enabled INTEGER NOT NULL DEFAULT 0 CHECK (totp_enabled IN (0, 1));

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

INSERT INTO schema_migration (name) VALUES ('011_add_local_password_totp_auth.sql');
COMMIT;
