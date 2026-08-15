"""Identity contract for release-bound and snapshot-bound demo artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.build_metadata import DEMO_SNAPSHOT_TAG, SEMVER_TAG, BuildMetadata


@dataclass(frozen=True)
class DemoIdentity:
    """One immutable source identity shared by a demo app/seed pair."""

    tag: str
    commit: str
    target_version: str
    identity: str
    oci_tag: str
    channel: str

    @classmethod
    def create(cls, tag: str, commit: str) -> DemoIdentity:
        snapshot = DEMO_SNAPSHOT_TAG.fullmatch(tag)
        if snapshot is not None:
            metadata = BuildMetadata.create(commit, tag, allow_demo_snapshot=True)
            target_version = snapshot.group(1)
            short_revision = snapshot.group(5)
            return cls(
                tag=tag,
                commit=commit,
                target_version=target_version,
                identity=metadata.identity,
                oci_tag=f"{target_version}-SNAPSHOT-{short_revision}",
                channel="snapshot",
            )
        if SEMVER_TAG.fullmatch(tag) is not None:
            metadata = BuildMetadata.create(commit, tag)
            return cls(
                tag=tag,
                commit=commit,
                target_version=tag,
                identity=metadata.identity,
                oci_tag=metadata.identity,
                channel="release",
            )
        raise ValueError("demo tag must identify a product release or demo snapshot")

    @property
    def product(self) -> dict[str, str]:
        return {
            "channel": self.channel,
            "commit": self.commit,
            "identity": self.identity,
            "tag": self.tag,
            "target_version": self.target_version,
            "version": self.identity,
        }

    @property
    def is_snapshot(self) -> bool:
        return self.channel == "snapshot"


STABLE_VERSION = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def version_key(value: str) -> tuple[int, int, int]:
    match = STABLE_VERSION.fullmatch(value)
    if match is None:
        raise ValueError("target version must be a stable SemVer tag")
    return tuple(int(match.group(index)) for index in range(1, 4))
