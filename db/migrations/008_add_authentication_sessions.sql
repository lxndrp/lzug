-- Add authentication identity state and opaque, revocable server sessions.
-- The bearer token and CSRF token are intentionally never stored in plaintext.
BEGIN TRANSACTION;

ALTER TABLE user_account RENAME TO user_account_legacy;

CREATE TABLE user_account (
  id INTEGER PRIMARY KEY,
  person_id INTEGER UNIQUE REFERENCES person(id) ON DELETE SET NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT,
  passkey_enabled INTEGER NOT NULL DEFAULT 0 CHECK (passkey_enabled IN (0, 1)),
  two_factor_enabled INTEGER NOT NULL DEFAULT 0 CHECK (two_factor_enabled IN (0, 1)),
  is_operator INTEGER NOT NULL DEFAULT 0 CHECK (is_operator IN (0, 1)),
  is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
  last_login_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (two_factor_enabled = 0 OR passkey_enabled = 1)
);

INSERT INTO user_account (
  id, person_id, email, password_hash, passkey_enabled, two_factor_enabled,
  last_login_at, created_at, updated_at
)
SELECT id, person_id, email, password_hash, passkey_enabled, two_factor_enabled,
       last_login_at, created_at, updated_at
FROM user_account_legacy;

DROP TABLE user_account_legacy;

CREATE TABLE auth_session (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_token_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  revoked_at TEXT,
  revoke_reason TEXT,
  rotated_from_id INTEGER REFERENCES auth_session(id) ON DELETE SET NULL,
  CHECK (expires_at > created_at),
  CHECK (revoked_at IS NULL OR revoked_at >= created_at)
);

CREATE INDEX auth_session_account_active
  ON auth_session(account_id, revoked_at, expires_at);

INSERT INTO schema_migration (name) VALUES ('008_add_authentication_sessions.sql');
COMMIT;
