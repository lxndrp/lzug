from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from backend.version import BuildMetadata


class BuildMetadataTests(unittest.TestCase):
    def test_development_identity_contains_the_full_commit(self) -> None:
        revision = "a" * 40
        metadata = BuildMetadata.create(revision)

        self.assertEqual(f"0.0.0-dev+sha.{revision}", metadata.identity)
        self.assertEqual(revision, metadata.revision)
        self.assertFalse(metadata.release)
        self.assertIsNone(metadata.tag)

    def test_stable_and_release_candidate_tags_are_supported(self) -> None:
        revision = "b" * 40
        for tag, identity in (("v1.2.3", "1.2.3"), ("v1.0.0-rc.1", "1.0.0-rc.1")):
            with self.subTest(tag=tag):
                metadata = BuildMetadata.create(revision, tag)
                self.assertEqual(identity, metadata.identity)
                self.assertTrue(metadata.release)
                self.assertEqual(tag, metadata.tag)

    def test_invalid_revisions_and_release_tags_fail_closed(self) -> None:
        for revision in ("", "a" * 39, "A" * 40, "unknown"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                BuildMetadata.create(revision)
        for tag in ("1.2.3", "v01.2.3", "v1.2.3-dev.1", "v1.2.3-rc.01", "latest"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                BuildMetadata.create("a" * 40, tag)

    def test_demo_snapshot_is_non_release_and_requires_explicit_opt_in(self) -> None:
        revision = "abcdef0123456789abcdef0123456789abcdef01"
        tag = "snapshot/v0.2.0-SNAPSHOT.abcdef0"
        with self.assertRaisesRegex(ValueError, "reserved for the demo assembly"):
            BuildMetadata.create(revision, tag)

        metadata = BuildMetadata.create(revision, tag, allow_demo_snapshot=True)

        self.assertEqual("v0.2.0-SNAPSHOT@abcdef0", metadata.identity)
        self.assertFalse(metadata.release)
        self.assertEqual(tag, metadata.tag)
        self.assertEqual(metadata, BuildMetadata.from_json(metadata.to_json()))

        with self.assertRaisesRegex(ValueError, "does not match"):
            BuildMetadata.create("0" * 40, tag, allow_demo_snapshot=True)

    def test_json_is_reproducible_and_rejects_inconsistent_identity(self) -> None:
        metadata = BuildMetadata.create("c" * 40)
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.json"
            second = Path(directory) / "second.json"
            metadata.write(first)
            metadata.write(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(metadata, BuildMetadata.read(first))

        tampered = metadata.to_json().replace("0.0.0-dev", "1.2.3")
        with self.assertRaises(ValueError):
            BuildMetadata.from_json(tampered)

    def test_component_cli_exports_explicit_identity_and_file(self) -> None:
        from backend.version import main

        output = StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(output):
            path = Path(directory) / "metadata.json"
            result = main(["--revision", "d" * 40, "--output", str(path), "--field", "identity"])
            exported = BuildMetadata.read(path)

        self.assertEqual(0, result)
        self.assertEqual(f"0.0.0-dev+sha.{'d' * 40}\n", output.getvalue())
        self.assertEqual(BuildMetadata.create("d" * 40), exported)

    def test_component_cli_requires_explicit_revision(self) -> None:
        from backend.version import main

        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
            main([])
        self.assertEqual(2, error.exception.code)


if __name__ == "__main__":
    unittest.main()
