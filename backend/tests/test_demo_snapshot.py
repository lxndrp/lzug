from __future__ import annotations

import unittest

from scripts.demo_snapshot import SnapshotContractError, snapshot_identity


class DemoSnapshotTests(unittest.TestCase):
    revision = "abcdef0123456789abcdef0123456789abcdef01"
    tag = "demo/v0.2.0-SNAPSHOT.abcdef0"

    def test_identity_is_derived_only_from_tag_and_matching_full_revision(self) -> None:
        identity = snapshot_identity(self.tag, self.revision)

        self.assertEqual("v0.2.0", identity.target_version)
        self.assertEqual("v0.2.0-SNAPSHOT@abcdef0", identity.identity)
        self.assertEqual("v0.2.0-SNAPSHOT-abcdef0", identity.oci_tag)
        self.assertEqual("snapshot", identity.channel)

        for tag, revision in (
            ("v0.2.0", self.revision),
            ("demo/v0.2.0-SNAPSHOT.abcdef", self.revision),
            ("demo/v0.2.0-SNAPSHOT.abcdef0", "0" * 40),
            ("demo/v0.2.0-nightly.abcdef0", self.revision),
        ):
            with self.subTest(tag=tag), self.assertRaises(SnapshotContractError):
                snapshot_identity(tag, revision)


if __name__ == "__main__":
    unittest.main()
