-- Add bounded worker claims for notification delivery processing.
BEGIN TRANSACTION;

DROP INDEX notification_delivery_due;

ALTER TABLE notification_delivery ADD COLUMN claim_token TEXT;
ALTER TABLE notification_delivery ADD COLUMN claimed_at TEXT;
ALTER TABLE notification_delivery ADD COLUMN claim_expires_at TEXT;

CREATE INDEX notification_delivery_due
  ON notification_delivery(status, next_attempt_at, claim_expires_at, id);

INSERT INTO schema_migration (name)
VALUES ('016_claim_notification_deliveries.sql');

COMMIT;
