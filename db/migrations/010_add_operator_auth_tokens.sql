-- Add single-use invitation and recovery material for the operator boundary.
-- Only SHA-256 token digests are persisted; plaintext tokens leave the service once.
BEGIN TRANSACTION;

CREATE TABLE auth_token (
  id INTEGER PRIMARY KEY,
  account_id INTEGER NOT NULL REFERENCES user_account(id) ON DELETE CASCADE,
  kind TEXT NOT NULL CHECK (kind IN ('invitation', 'recovery')),
  token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash) = 64),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  consumed_at TEXT,
  CHECK (expires_at > created_at),
  CHECK (consumed_at IS NULL OR consumed_at >= created_at)
);

CREATE INDEX auth_token_account_kind
  ON auth_token(account_id, kind, expires_at);

-- There is exactly one bootstrap operator; later invitations are non-operator
-- accounts and therefore do not consume this uniqueness slot.
CREATE UNIQUE INDEX user_account_one_operator
  ON user_account(is_operator)
  WHERE is_operator = 1;

INSERT INTO schema_migration (name) VALUES ('010_add_operator_auth_tokens.sql');
COMMIT;
