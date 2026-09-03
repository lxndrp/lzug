from __future__ import annotations

import base64
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path

from backend.admin import EXIT_CONFLICT, EXIT_OK, run
from backend.backup_recipients import BackupRecipientRepository, recipient_fingerprint
from backend.backup_restore import BACKUP_PUBLIC_KEY_ENV, ArtifactError, ArtifactService
from backend.database import PersistencePaths, initialize

RECIPIENT = "age1wkdx2jsjtg5wg2ts5ptcalmqvtdp9uwwplhl6yyraalr9g9l5gxqh4qu5t"
SECOND_RECIPIENT = "age10cqdlzak8hxw3sz5nrrr7u6y6v2pt8n6pj3ultl98ety0fkw2pzqqzkst0"


class BackupRecipientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.paths = PersistencePaths(
            data_dir=root,
            database=root / "lzug.sqlite",
            documents=root / "documents",
            backups=root / "backups",
        )
        self.paths.documents.mkdir()
        self.paths.backups.mkdir()
        initialize(self.paths.database, with_seed=False, reset=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_set_show_replace_and_append_only_audit(self) -> None:
        repository = BackupRecipientRepository(self.paths.database)
        self.assertIsNone(repository.show())

        current = repository.set(RECIPIENT, recipient_fingerprint(RECIPIENT))
        self.assertEqual(RECIPIENT, current["recipient"])
        self.assertEqual("age-x25519-v1", current["protection"])
        with self.assertRaises(ArtifactError) as duplicate:
            repository.set(RECIPIENT, recipient_fingerprint(RECIPIENT))
        self.assertEqual("recipient_already_configured", duplicate.exception.code)

        replaced = repository.replace(
            SECOND_RECIPIENT,
            recipient_fingerprint(SECOND_RECIPIENT),
        )
        self.assertEqual(current["fingerprint"], replaced["previous_fingerprint"])
        with closing(sqlite3.connect(self.paths.database)) as connection:
            audit = connection.execute(
                "SELECT action, previous_fingerprint, fingerprint "
                "FROM backup_recipient_audit ORDER BY id"
            ).fetchall()
        self.assertEqual(["set", "replace"], [row[0] for row in audit])
        self.assertIsNone(audit[0][1])

    def test_fingerprint_mismatch_and_invalid_recipient_fail_closed(self) -> None:
        repository = BackupRecipientRepository(self.paths.database)
        with self.assertRaises(ArtifactError) as mismatch:
            repository.set(RECIPIENT, "sha256:" + "0" * 64)
        self.assertEqual("recipient_key_mismatch", mismatch.exception.code)
        with self.assertRaises(ArtifactError) as invalid:
            repository.set("not-an-age-recipient", "sha256:" + "0" * 64)
        self.assertEqual("recipient_key_invalid", invalid.exception.code)

    def test_concurrent_initial_set_has_one_winner_and_one_stable_conflict(self) -> None:
        barrier = threading.Barrier(2)
        outcomes: list[str] = []

        def set_recipient() -> None:
            repository = BackupRecipientRepository(self.paths.database)
            barrier.wait(timeout=2)
            try:
                repository.set(RECIPIENT, recipient_fingerprint(RECIPIENT))
                outcomes.append("ok")
            except ArtifactError as error:
                outcomes.append(error.code)

        threads = [threading.Thread(target=set_recipient) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertEqual(["ok", "recipient_already_configured"], sorted(outcomes))
        with closing(sqlite3.connect(self.paths.database)) as connection:
            self.assertEqual(
                1,
                connection.execute("SELECT count(*) FROM backup_recipient_audit").fetchone()[0],
            )

    def test_legacy_public_environment_value_migrates_once(self) -> None:
        raw = bytes(range(32))
        legacy = "x25519:" + base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        repository = BackupRecipientRepository(
            self.paths.database,
            environment={BACKUP_PUBLIC_KEY_ENV: legacy},
        )
        migrated = repository.show()
        self.assertIsNotNone(migrated)
        self.assertTrue(migrated["recipient"].startswith("age1"))
        repository.show()
        with closing(sqlite3.connect(self.paths.database)) as connection:
            count = connection.execute(
                "SELECT count(*) FROM backup_recipient_audit WHERE action = 'migrate'"
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_set_cannot_bypass_legacy_environment_migration(self) -> None:
        raw = bytes(range(32))
        legacy = "x25519:" + base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
        repository = BackupRecipientRepository(
            self.paths.database,
            environment={BACKUP_PUBLIC_KEY_ENV: legacy},
        )

        with self.assertRaises(ArtifactError) as conflict:
            repository.set(RECIPIENT, recipient_fingerprint(RECIPIENT))

        self.assertEqual("recipient_already_configured", conflict.exception.code)
        self.assertNotEqual(RECIPIENT, repository.show()["recipient"])

    def test_admin_protocol_persists_only_public_recipient_fields(self) -> None:
        artifacts = ArtifactService(
            self.paths,
            environment={},
        )
        arguments = {
            "recipient": RECIPIENT,
            "fingerprint": recipient_fingerprint(RECIPIENT),
        }
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(
                json.dumps(
                    {
                        "version": 1,
                        "command": "backup-recipient-set",
                        "arguments": arguments,
                    }
                ).encode(),
                artifacts=artifacts,
            )
        stdout.flush()
        self.assertEqual(EXIT_OK, code)
        self.assertNotIn("private", output.getvalue().decode())

        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(
                json.dumps(
                    {
                        "version": 1,
                        "command": "backup-recipient-set",
                        "arguments": arguments,
                    }
                ).encode(),
                artifacts=artifacts,
            )
        stdout.flush()
        self.assertEqual(EXIT_CONFLICT, code)

    def test_admin_protocol_rejects_private_material_as_unknown_argument(self) -> None:
        artifacts = ArtifactService(self.paths, environment={})
        output = io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding="utf-8")
        with redirect_stdout(stdout):
            code = run(
                json.dumps(
                    {
                        "version": 1,
                        "command": "backup-recipient-set",
                        "arguments": {
                            "recipient": RECIPIENT,
                            "fingerprint": recipient_fingerprint(RECIPIENT),
                            "recipient_private_key": "forbidden-secret",
                        },
                    }
                ).encode(),
                artifacts=artifacts,
            )
        stdout.flush()
        self.assertEqual(20, code)
        self.assertNotIn("forbidden-secret", output.getvalue().decode())


if __name__ == "__main__":
    unittest.main()
