from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import version
from backend.build_metadata import BuildMetadata


class VersionTests(unittest.TestCase):
    def tearDown(self) -> None:
        version.build_metadata.cache_clear()

    def test_injected_metadata_is_read_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "build-metadata.json"
            BuildMetadata.create("a" * 40).write(metadata)
            version.build_metadata.cache_clear()

            with patch.object(version, "BUILD_METADATA_PATH", metadata):
                self.assertEqual(f"0.0.0-dev+sha.{'a' * 40}", version.application_version())
                self.assertEqual("a" * 40, version.build_revision())
                metadata.unlink()
                self.assertEqual("a" * 40, version.build_revision())

    def test_packaged_release_metadata_is_the_only_runtime_version_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "build-metadata.json"
            BuildMetadata.create("b" * 40, "v1.2.3").write(metadata)
            version.build_metadata.cache_clear()

            with patch.object(version, "BUILD_METADATA_PATH", metadata):
                self.assertEqual("1.2.3", version.application_version())
                self.assertEqual("b" * 40, version.build_revision())


if __name__ == "__main__":
    unittest.main()
