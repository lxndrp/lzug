"""Preflight and reporting helpers for the legacy exam-location migration."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unicodedata
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MIGRATION_NAME = "025_model_exam_venues.sql"
MACHINE_REPORT_NAME = "exam-venue-migration-025.json"
HUMAN_REPORT_NAME = "exam-venue-migration-025.txt"


class ExamVenueMigrationConflictError(ValueError):
    """Reject ambiguous legacy venue data before the SQL migration starts."""


@dataclass(frozen=True)
class ExamVenueMigrationPreparation:
    """Values exposed to the atomic SQL migration through SQLite functions."""

    machine_report: str
    human_report: str
    backup_reference: str


def normalize_migration_text(value: Any) -> str:
    """Return the stable Unicode/case/whitespace key used for exact grouping."""
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return " ".join(normalized.split()).casefold()


def migrate_plan_reference_json(raw: str) -> str:
    """Rename legacy location references recursively without changing their IDs."""
    value = json.loads(raw)

    def migrate(item: Any) -> Any:
        if isinstance(item, list):
            return [migrate(entry) for entry in item]
        if not isinstance(item, dict):
            return item
        migrated = {key: migrate(entry) for key, entry in item.items()}
        for old, new in (
            ("location_id", "room_id"),
            ("default_location_id", "default_room_id"),
        ):
            if old not in migrated:
                continue
            if new in migrated and migrated[new] != migrated[old]:
                raise ValueError(f"Conflicting plan references: {old} and {new}")
            migrated[new] = migrated.pop(old)
        return migrated

    return json.dumps(
        migrate(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def prepare_exam_venue_migration(
    db_path: Path,
    backup_path: Path,
    report_directory: Path,
) -> ExamVenueMigrationPreparation:
    """Inspect legacy rows and publish deterministic machine and human reports."""
    if backup_path.is_symlink() or not backup_path.is_file():
        raise ExamVenueMigrationConflictError("Exam-venue migration requires a verified backup")
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "location" not in tables:
            raise ExamVenueMigrationConflictError("Legacy location table is unavailable")
        locations = [
            dict(row)
            for row in connection.execute(
                "SELECT id, committee_id, name, street, postal_code, city, room, "
                "is_active, created_at, updated_at FROM location ORDER BY id"
            )
        ]
        committees = {row[0] for row in connection.execute("SELECT id FROM committee")}
        planning_references = [
            {"planning_settings_id": row[0], "legacy_location_id": row[1]}
            for row in connection.execute(
                "SELECT id, default_location_id FROM planning_settings "
                "WHERE default_location_id IS NOT NULL ORDER BY id"
            )
        ]
        day_references = [
            {"exam_day_id": row[0], "legacy_location_id": row[1]}
            for row in connection.execute("SELECT id, location_id FROM exam_day ORDER BY id")
        ]
        plan_revisions = (
            [
                {
                    "confirmed_plan_revision_id": row[0],
                    "before_state_json": row[1],
                    "after_state_json": row[2],
                }
                for row in connection.execute(
                    "SELECT id, before_state_json, after_state_json "
                    "FROM confirmed_plan_revision ORDER BY id"
                )
            ]
            if "confirmed_plan_revision" in tables
            else []
        )

    location_ids = {int(row["id"]) for row in locations}
    conflicts: list[dict[str, Any]] = []
    for row in locations:
        if int(row["committee_id"]) not in committees:
            conflicts.append(
                {
                    "code": "orphan_committee",
                    "legacy_location_id": int(row["id"]),
                    "committee_id": int(row["committee_id"]),
                }
            )
    for kind, references, id_field in (
        ("orphan_planning_default", planning_references, "planning_settings_id"),
        ("orphan_exam_day", day_references, "exam_day_id"),
    ):
        for reference in references:
            if int(reference["legacy_location_id"]) not in location_ids:
                conflicts.append(
                    {
                        "code": kind,
                        id_field: int(reference[id_field]),
                        "legacy_location_id": int(reference["legacy_location_id"]),
                    }
                )

    for revision in plan_revisions:
        for field in ("before_state_json", "after_state_json"):
            try:
                migrate_plan_reference_json(str(revision[field]))
            except (TypeError, ValueError, json.JSONDecodeError) as error:
                conflicts.append(
                    {
                        "code": "invalid_plan_reference",
                        "confirmed_plan_revision_id": revision["confirmed_plan_revision_id"],
                        "field": field,
                        "error": str(error),
                    }
                )

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in locations:
        normalized = tuple(
            normalize_migration_text(row[field])
            for field in ("name", "street", "postal_code", "city")
        )
        key: tuple[Any, ...]
        if all(normalized):
            key = ("complete", int(row["committee_id"]), *normalized, "deutschland")
        else:
            key = ("incomplete", int(row["id"]))
        grouped[key].append(row)

    groups: list[dict[str, Any]] = []
    clarifications: list[dict[str, Any]] = []
    for rows in sorted(
        grouped.values(), key=lambda entries: min(int(row["id"]) for row in entries)
    ):
        venue_id = min(int(row["id"]) for row in rows)
        room_names: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            room = str(row["room"] or "").strip() or "Gesamter Standort"
            room_names[normalize_migration_text(room)].append(int(row["id"]))
        for normalized_room, legacy_ids in sorted(room_names.items()):
            if len(legacy_ids) > 1:
                conflicts.append(
                    {
                        "code": "duplicate_room_name",
                        "target_venue_id": venue_id,
                        "normalized_room_name": normalized_room,
                        "legacy_location_ids": sorted(legacy_ids),
                    }
                )
        legacy_ids = sorted(int(row["id"]) for row in rows)
        representative = min(rows, key=lambda row: int(row["id"]))
        groups.append(
            {
                "target_venue_id": venue_id,
                "committee_id": int(representative["committee_id"]),
                "name": str(representative["name"]),
                "legacy_location_ids": legacy_ids,
                "grouped": len(legacy_ids) > 1,
            }
        )
        clarifications.append(
            {
                "code": "accessibility_missing",
                "target_venue_id": venue_id,
                "legacy_location_ids": legacy_ids,
            }
        )

    venue_names: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for group in groups:
        venue_names[(group["committee_id"], normalize_migration_text(group["name"]))].append(group)
    for (committee_id, normalized_name), matching_groups in sorted(venue_names.items()):
        if len(matching_groups) > 1:
            conflicts.append(
                {
                    "code": "duplicate_venue_name",
                    "committee_id": committee_id,
                    "normalized_venue_name": normalized_name,
                    "target_venue_ids": sorted(
                        int(group["target_venue_id"]) for group in matching_groups
                    ),
                    "legacy_location_ids": sorted(
                        legacy_id
                        for group in matching_groups
                        for legacy_id in group["legacy_location_ids"]
                    ),
                }
            )

    report = {
        "format": "lzug-exam-venue-migration-report",
        "format_version": 1,
        "migration": MIGRATION_NAME,
        "backup": {"reference": backup_path.name, "verified": True},
        "source": {
            "locations": len(locations),
            "planning_defaults": len(planning_references),
            "exam_days": len(day_references),
            "confirmed_plan_revisions": len(plan_revisions),
        },
        "target": {
            "venues": len(groups),
            "rooms": len(locations),
            "legacy_mappings": len(locations),
            "grouped_legacy_locations": len(locations) - len(groups),
        },
        "groups": groups,
        "conflicts": sorted(conflicts, key=lambda item: json.dumps(item, sort_keys=True)),
        "clarifications": clarifications,
    }
    machine = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    human = _human_report(report)
    report_directory.mkdir(parents=True, exist_ok=True)
    _atomic_text(report_directory / MACHINE_REPORT_NAME, machine)
    _atomic_text(report_directory / HUMAN_REPORT_NAME, human)
    if conflicts:
        raise ExamVenueMigrationConflictError(
            "Legacy exam-location migration has conflicts; inspect "
            f"{MACHINE_REPORT_NAME} or {HUMAN_REPORT_NAME}"
        )
    return ExamVenueMigrationPreparation(machine, human, backup_path.name)


def _human_report(report: dict[str, Any]) -> str:
    source = report["source"]
    target = report["target"]
    lines = [
        "lzug Bestandsmigration Prüfungsorte, Räume und Kontakte",
        "",
        f"Migration: {report['migration']}",
        f"Geprüftes Backup: {report['backup']['reference']}",
        f"Altorte: {source['locations']}",
        f"Planungs-Standardreferenzen: {source['planning_defaults']}",
        f"Prüfungstagsreferenzen: {source['exam_days']}",
        f"Neue Prüfungsorte: {target['venues']}",
        f"Neue Räume: {target['rooms']}",
        f"Gruppierte Altorte: {target['grouped_legacy_locations']}",
        f"Konflikte: {len(report['conflicts'])}",
        f"Klärungsfälle Barrierefreiheit: {len(report['clarifications'])}",
        "",
        "Gruppierungen:",
    ]
    lines.extend(
        f"- Ort {group['target_venue_id']} ({group['name']}): Alt-IDs "
        + ", ".join(str(value) for value in group["legacy_location_ids"])
        for group in report["groups"]
    )
    lines.append("")
    lines.append("Konflikte:")
    if report["conflicts"]:
        lines.extend(
            f"- {item['code']}: {json.dumps(item, ensure_ascii=False, sort_keys=True)}"
            for item in report["conflicts"]
        )
    else:
        lines.append("- keine")
    lines.append("")
    return "\n".join(lines) + "\n"


def _atomic_text(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
