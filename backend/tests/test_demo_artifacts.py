from __future__ import annotations

import json
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
    initialize_workdir,
    sha256_file,
    validate_runtime_binding,
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
            loaded_app, loaded_seed = validate_runtime_binding(app_manifest, data_dir)
            self.assertEqual(self.product_commit, loaded_app["product"]["commit"])
            self.assertEqual(first["seed_revision"], loaded_seed["seed_revision"])

            ResourceRepository(data_dir / "lzug.sqlite").update(
                CANDIDATE, 1, {"last_name": "Laufende Änderung"}
            )
            restarted_app, restarted_seed = validate_runtime_binding(app_manifest, data_dir)
            self.assertEqual(loaded_app, restarted_app)
            self.assertEqual(loaded_seed, restarted_seed)

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

            with self.assertRaisesRegex(DemoArtifactError, "different product tags"):
                validate_runtime_binding(app_manifest, data_dir)

    @staticmethod
    def _scalar(database: Path, query: str):
        import sqlite3

        with sqlite3.connect(database) as connection:
            return connection.execute(query).fetchone()[0]


if __name__ == "__main__":
    unittest.main()
