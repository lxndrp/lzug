from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from backend.auth import AuthenticationRepository
from backend.models import CANDIDATE
from backend.repositories import ResourceRepository
from demo.artifacts import (
    DemoArtifactError,
    build_app_manifest,
    build_seed,
    canonical_digest,
    initialize_workdir,
    sha256_file,
    validate_runtime_binding,
    verify_seed,
)


class DemoArtifactTests(unittest.TestCase):
    product_tag = "v0.1.1"
    product_commit = "948cab736131894950dbad57533e80f7238dd545"

    def test_seed_and_manifest_are_reproducible_and_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_db = root / "first.sqlite"
            second_db = root / "second.sqlite"
            first_manifest = root / "first.json"
            second_manifest = root / "second.json"
            app_manifest = root / "app.json"

            first = build_seed(
                Path("."),
                first_db,
                first_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            second = build_seed(
                Path("."),
                second_db,
                second_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            build_app_manifest(
                Path("."),
                app_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )

            self.assertEqual(first, second)
            self.assertEqual(sha256_file(first_db), sha256_file(second_db))
            self.assertEqual(first_manifest.read_bytes(), second_manifest.read_bytes())
            self.assertEqual(first["snapshot_sha256"], sha256_file(first_db))
            self.assertRegex(first["seed_revision"], r"^[0-9a-f]{64}$")
            self.assertEqual(2, self._scalar(first_db, "SELECT COUNT(*) FROM user_account"))

            data_dir = root / "data"
            initialize_workdir(first_db, first_manifest, data_dir)
            runtime_status = json.loads(
                (data_dir / "demo-runtime-status.json").read_text(encoding="utf-8")
            )
            self.assertTrue(runtime_status["initialized"])
            self.assertEqual("ready", runtime_status["initialization_status"])
            self.assertEqual(first["seed_revision"], runtime_status["seed_revision"])
            self.assertEqual(runtime_status["initialized_at"], runtime_status["last_reset_at"])
            loaded_app, loaded_seed = validate_runtime_binding(app_manifest, data_dir)
            self.assertEqual(self.product_commit, loaded_app["product"]["commit"])
            self.assertEqual(first["seed_revision"], loaded_seed["seed_revision"])

            ResourceRepository(data_dir / "lzug.sqlite").update(
                CANDIDATE, 1, {"last_name": "Laufende Änderung"}
            )
            restarted_app, restarted_seed = validate_runtime_binding(app_manifest, data_dir)
            self.assertEqual(loaded_app, restarted_app)
            self.assertEqual(loaded_seed, restarted_seed)

    def test_publish_verification_rejects_self_consistent_environment_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected_database = root / "expected.sqlite"
            expected_manifest_path = root / "expected.json"
            expected_manifest = build_seed(
                Path("."),
                expected_database,
                expected_manifest_path,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            drift_database = root / "drift.sqlite"
            shutil.copyfile(expected_database, drift_database)
            with sqlite3.connect(drift_database) as connection:
                self.assertEqual(
                    ("delete",), connection.execute("PRAGMA journal_mode = DELETE").fetchone()
                )
                connection.execute("PRAGMA page_size = 8192")
                connection.execute("VACUUM")
                self.assertEqual((8192,), connection.execute("PRAGMA page_size").fetchone())
                self.assertEqual(("ok",), connection.execute("PRAGMA integrity_check").fetchone())
            self.assertNotEqual(sha256_file(expected_database), sha256_file(drift_database))
            drift_manifest = {**expected_manifest, "snapshot_sha256": sha256_file(drift_database)}
            drift_binding = {
                key: value for key, value in drift_manifest.items() if key != "seed_revision"
            }
            drift_manifest["seed_revision"] = canonical_digest(drift_binding)
            drift_manifest_path = root / "drift.json"
            drift_manifest_path.write_text(
                json.dumps(drift_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(
                drift_manifest,
                verify_seed(drift_database, drift_manifest_path),
            )
            with self.assertRaisesRegex(DemoArtifactError, "expected manifest"):
                verify_seed(
                    drift_database,
                    drift_manifest_path,
                    expected_manifest_path=expected_manifest_path,
                )
            with self.assertRaisesRegex(DemoArtifactError, "expected revision"):
                verify_seed(
                    drift_database,
                    drift_manifest_path,
                    expected_revision=expected_manifest["seed_revision"],
                )

    def test_init_reset_removes_changes_files_and_old_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_db = root / "seed.sqlite"
            seed_manifest = root / "seed.json"
            build_seed(
                Path("."),
                seed_db,
                seed_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            data_dir = root / "data"
            initialize_workdir(seed_db, seed_manifest, data_dir)
            database = data_dir / "lzug.sqlite"
            credentials = AuthenticationRepository(database).create_session(1)
            ResourceRepository(database).update(CANDIDATE, 1, {"last_name": "Geändert"})
            (data_dir / "documents" / "temporary.txt").write_text("demo", encoding="utf-8")

            initialize_workdir(seed_db, seed_manifest, data_dir)

            self.assertEqual(
                "Alpha", self._scalar(database, "SELECT last_name FROM candidate WHERE id = 1")
            )
            self.assertFalse((data_dir / "documents" / "temporary.txt").exists())
            self.assertIsNone(AuthenticationRepository(database).authenticate(credentials.token))
            self.assertEqual(sha256_file(seed_db), sha256_file(database))

    def test_runtime_validation_fails_closed_for_mismatched_product(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_db = root / "seed.sqlite"
            seed_manifest = root / "seed.json"
            app_manifest = root / "app.json"
            build_seed(
                Path("."),
                seed_db,
                seed_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            build_app_manifest(
                Path("."),
                app_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            data_dir = root / "data"
            initialize_workdir(seed_db, seed_manifest, data_dir)
            value = json.loads(app_manifest.read_text(encoding="utf-8"))
            value["product"]["tag"] = "v0.1.2"
            app_manifest.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(DemoArtifactError, "different product identities"):
                validate_runtime_binding(app_manifest, data_dir)

    def test_snapshot_manifests_bind_non_release_identity_and_target_version(self) -> None:
        revision = "abcdef0123456789abcdef0123456789abcdef01"
        tag = "demo/v0.2.0-SNAPSHOT.abcdef0"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed = build_seed(
                Path("."),
                root / "seed.sqlite",
                root / "seed.json",
                product_tag=tag,
                product_commit=revision,
            )
            app = build_app_manifest(
                Path("."),
                root / "app.json",
                product_tag=tag,
                product_commit=revision,
            )

        expected = {
            "channel": "snapshot",
            "commit": revision,
            "identity": "v0.2.0-SNAPSHOT@abcdef0",
            "tag": tag,
            "target_version": "v0.2.0",
            "version": "v0.2.0-SNAPSHOT@abcdef0",
        }
        self.assertEqual(expected, seed["product"])
        self.assertEqual(expected, app["product"])

    def test_runtime_validation_fails_closed_without_matching_init_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            seed_db = root / "seed.sqlite"
            seed_manifest = root / "seed.json"
            app_manifest = root / "app.json"
            manifest = build_seed(
                Path("."),
                seed_db,
                seed_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            build_app_manifest(
                Path("."),
                app_manifest,
                product_tag=self.product_tag,
                product_commit=self.product_commit,
            )
            data_dir = root / "data"
            initialize_workdir(seed_db, seed_manifest, data_dir)
            runtime_status_path = data_dir / "demo-runtime-status.json"
            runtime_status = json.loads(runtime_status_path.read_text(encoding="utf-8"))
            runtime_status["seed_revision"] = "0" * 64
            runtime_status_path.write_text(json.dumps(runtime_status), encoding="utf-8")

            with self.assertRaisesRegex(DemoArtifactError, "different seed revision"):
                validate_runtime_binding(app_manifest, data_dir)

            runtime_status["seed_revision"] = manifest["seed_revision"]
            runtime_status_path.write_text(json.dumps(runtime_status), encoding="utf-8")
            runtime_status_path.unlink()
            with self.assertRaisesRegex(DemoArtifactError, "Could not read demo runtime status"):
                validate_runtime_binding(app_manifest, data_dir)

    @staticmethod
    def _scalar(database: Path, query: str):
        import sqlite3

        with sqlite3.connect(database) as connection:
            return connection.execute(query).fetchone()[0]


if __name__ == "__main__":
    unittest.main()
