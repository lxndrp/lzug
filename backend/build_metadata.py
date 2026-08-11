"""Canonical build identity shared by every lzug artifact."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
SEMVER_TAG = re.compile(
    r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)" r"(?:-rc\.(0|[1-9][0-9]*))?$"
)


@dataclass(frozen=True)
class BuildMetadata:
    """Immutable identity derived exclusively from a commit and optional release tag."""

    identity: str
    revision: str
    release: bool
    tag: str | None

    @classmethod
    def create(cls, revision: str, tag: str | None = None) -> BuildMetadata:
        """Create validated metadata for a development or tagged release build."""

        if COMMIT_SHA.fullmatch(revision) is None:
            raise ValueError("revision must contain exactly 40 lowercase hex characters")
        if tag is None:
            return cls(
                identity=f"0.0.0-dev+sha.{revision}",
                revision=revision,
                release=False,
                tag=None,
            )

        match = SEMVER_TAG.fullmatch(tag)
        if match is None:
            raise ValueError(
                "release tag must be SemVer in the form "
                "vMAJOR.MINOR.PATCH or vMAJOR.MINOR.PATCH-rc.N"
            )
        return cls(identity=tag.removeprefix("v"), revision=revision, release=True, tag=tag)

    @classmethod
    def from_json(cls, payload: str) -> BuildMetadata:
        """Parse metadata and reject unknown, missing, or inconsistent fields."""

        value = json.loads(payload)
        if not isinstance(value, dict) or set(value) != {"identity", "revision", "release", "tag"}:
            raise ValueError("build metadata must contain identity, revision, release, and tag")
        if not isinstance(value["revision"], str):
            raise ValueError("build metadata revision must be a string")
        if not isinstance(value["release"], bool):
            raise ValueError("build metadata release must be a boolean")
        if value["tag"] is not None and not isinstance(value["tag"], str):
            raise ValueError("build metadata tag must be a string or null")
        expected = cls.create(value["revision"], value["tag"])
        if value["identity"] != expected.identity or value["release"] != expected.release:
            raise ValueError("build metadata fields do not describe one canonical identity")
        return expected

    @classmethod
    def read(cls, path: Path) -> BuildMetadata:
        """Read and validate one canonical metadata file."""

        return cls.from_json(path.read_text(encoding="utf-8"))

    def to_json(self) -> str:
        """Render byte-stable JSON for embedding in all artifacts."""

        return (
            json.dumps(asdict(self), ensure_ascii=True, separators=(",", ":"), sort_keys=True)
            + "\n"
        )

    def write(self, path: Path) -> None:
        """Write byte-stable metadata, creating the destination directory if needed."""

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
