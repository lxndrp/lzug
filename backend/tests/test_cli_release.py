from __future__ import annotations

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from backend.build_metadata import BuildMetadata
from scripts.build_cli_release import (
    CLI_TARGETS,
    archive_binary,
    build_command,
    build_release,
    checksums_name,
)


class CliReleaseBuilderTests(unittest.TestCase):
    def test_matrix_contains_exactly_six_native_targets(self) -> None:
        self.assertEqual(
            {
                ("linux", "amd64"),
                ("linux", "arm64"),
                ("darwin", "amd64"),
                ("darwin", "arm64"),
                ("windows", "amd64"),
                ("windows", "arm64"),
            },
            {(goos, goarch) for goos, goarch, _ in CLI_TARGETS},
        )
        self.assertEqual("lzug-admin-1.2.3.checksums.txt", checksums_name("1.2.3"))

    def test_go_command_is_reproducible_and_identity_complete(self) -> None:
        metadata = BuildMetadata.create("a" * 40, "v1.2.3")
        command = build_command(Path("dist/lzug-admin"), "linux", "amd64", metadata)

        self.assertIn("-trimpath", command)
        self.assertIn("-buildvcs=false", command)
        self.assertIn("-ldflags=-buildid= -s -w", command[4])
        self.assertIn("-X main.applicationVersion=1.2.3", command[4])
        self.assertIn("-X main.applicationRevision=" + "a" * 40, command[4])
        self.assertIn("-X main.applicationTag=v1.2.3", command[4])

    def test_tar_and_zip_archives_are_byte_stable_and_carry_metadata(self) -> None:
        metadata = BuildMetadata.create("b" * 40, "v1.2.3")
        source = Path(self.id().replace(".", "_") + ".binary")
        source.write_bytes(b"binary")
        self.addCleanup(source.unlink)

        first = Path(self.id().replace(".", "_") + ".tar.gz")
        second = Path(self.id().replace(".", "_") + ".tar.gz.2")
        zip_path = Path(self.id().replace(".", "_") + ".zip")
        self.addCleanup(first.unlink)
        self.addCleanup(second.unlink)
        self.addCleanup(zip_path.unlink)

        archive_binary(source, metadata, "linux", "amd64", "tar.gz", first)
        archive_binary(source, metadata, "linux", "amd64", "tar.gz", second)
        archive_binary(source, metadata, "windows", "amd64", "zip", zip_path)
        self.assertEqual(first.read_bytes(), second.read_bytes())

        with tarfile.open(fileobj=io.BytesIO(first.read_bytes()), mode="r:gz") as archive:
            self.assertEqual(
                ["lzug-admin", "build-metadata.json"],
                archive.getnames(),
            )
            metadata_file = archive.extractfile("build-metadata.json")
            self.assertIsNotNone(metadata_file)
            self.assertEqual(metadata.to_json().encode(), metadata_file.read())

        with zipfile.ZipFile(zip_path) as archive:
            self.assertEqual(["lzug-admin.exe", "build-metadata.json"], archive.namelist())
            self.assertEqual(metadata.to_json().encode(), archive.read("build-metadata.json"))

    def test_failed_partial_build_does_not_publish_archives(self) -> None:
        revision = "c" * 40
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "release-assets" / "cli"
            work = root / "work"
            calls = 0

            def fail_on_second_build(
                binary: Path, goos: str, goarch: str, metadata: BuildMetadata
            ) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise RuntimeError("simulated missing target")
                binary.write_bytes(b"binary")

            with mock.patch(
                "scripts.build_cli_release._run_build", side_effect=fail_on_second_build
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated missing target"):
                    build_release("0.0.0-dev+sha." + revision, revision, None, output, work)

            self.assertEqual([], list(output.iterdir()))


if __name__ == "__main__":
    unittest.main()
