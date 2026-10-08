"""Typed consequence descriptions for venue and room changes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from backend.planning_ports import VenueAuditEventSnapshot, VenueRepository

CALENDAR_VENUE_FIELDS = frozenset(
    {
        "name",
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
    }
)
CALENDAR_ROOM_FIELDS = frozenset(
    {"name", "building", "wing", "floor", "room_number", "access_notes"}
)
NOTIFICATION_VENUE_FIELDS = frozenset(
    {
        "street",
        "postal_code",
        "city",
        "country",
        "site_name",
        "entrance",
        "travel_directions",
        "is_accessible",
        "accessibility_status",
        "accessibility_notes",
    }
)
NOTIFICATION_ROOM_FIELDS = frozenset(
    {"name", "building", "wing", "floor", "room_number", "access_notes"}
)
FIELD_LABELS = {
    "name": "Bezeichnung",
    "street": "Anschrift",
    "postal_code": "Anschrift",
    "city": "Anschrift",
    "country": "Anschrift",
    "site_name": "Standort",
    "entrance": "Eingang oder Treffpunkt",
    "travel_directions": "Anreise- oder Auffindungshinweis",
    "building": "Gebäude",
    "wing": "Trakt",
    "floor": "Etage",
    "room_number": "Raumnummer",
    "access_notes": "Zugangs- oder Auffindungshinweis",
    "is_accessible": "Barrierefreiheit",
    "accessibility_status": "Barrierefreiheit",
    "accessibility_notes": "Barrierefreiheitshinweis",
}


@dataclass(frozen=True)
class VenueAssignment:
    assignment_id: int
    recipient_member_id: int
    committee_id: int


@dataclass(frozen=True)
class VenueCalendarConsequence:
    recipient_member_id: int
    assignment_id: int
    entity_type: str
    entity_id: int
    expected_signature: tuple[tuple[str, object], ...]


@dataclass(frozen=True)
class VenueNotificationConsequence:
    recipient_member_id: int
    assignment_ids: tuple[int, ...]
    committee_id: int
    venue_id: int
    entity_type: str
    entity_id: int
    expected_signature: tuple[tuple[str, object], ...]
    fields: tuple[str, ...]


@dataclass(frozen=True)
class VenueConsequenceDescriptions:
    calendar: tuple[VenueCalendarConsequence, ...]
    notifications: tuple[VenueNotificationConsequence, ...]
    calendar_fields: tuple[str, ...]
    notification_fields: tuple[str, ...]


@dataclass(frozen=True)
class VenueAuditConsequenceSource:
    audit: VenueAuditEventSnapshot
    descriptions: VenueConsequenceDescriptions


class PlanningVenueConsequencePlanner:
    """Read Planning facts and derive typed, deterministic venue consequences."""

    def __init__(self, repository: VenueRepository) -> None:
        self.repository = repository

    def preview(
        self,
        *,
        venue_id: int,
        entity_type: str,
        entity_id: int,
        before: Mapping[str, object],
        after: Mapping[str, object],
        meaningful_change: bool = True,
        today: date | None = None,
    ) -> dict:
        changed_fields = {key for key in before if before.get(key) != after.get(key)}
        calendar_fields = changed_fields & calendar_fields_for(entity_type)
        notification_fields = changed_fields & notification_fields_for(entity_type)
        if not meaningful_change:
            notification_fields.clear()
        assignments = self.repository.future_assignments(
            venue_id,
            room_id=entity_id if entity_type == "room" else None,
            today=(today or date.today()).isoformat(),
        )
        dates = [assignment.date for assignment in assignments]
        recipient_count = len({assignment.recipient_member_id for assignment in assignments})
        assignment_count = len(assignments)
        return {
            "count": assignment_count,
            "date_from": min(dates, default=None),
            "date_to": max(dates, default=None),
            "requires_confirmation": bool(assignment_count and changed_fields),
            "calendar": {
                "event_count": assignment_count if calendar_fields else 0,
                "fields": list(labels_for(frozenset(calendar_fields))),
            },
            "notifications": {
                "recipient_count": recipient_count if notification_fields else 0,
                "fields": list(labels_for(frozenset(notification_fields))),
            },
        }

    def audits_for_venue(self, venue_id: int) -> tuple[VenueAuditEventSnapshot, ...]:
        return self.repository.consequence_audits_for_venue(venue_id)

    def consequence_audits(self) -> tuple[VenueAuditEventSnapshot, ...]:
        return self.repository.consequence_audits()

    def source_for_audit(self, audit_id: int, *, today: date | None = None):
        audit = self.repository.consequence_audit(audit_id)
        if audit is None:
            return None
        try:
            details = json.loads(audit.details_json)
        except TypeError, json.JSONDecodeError:
            details = {}
        if not isinstance(details, dict):
            details = {}
        if details.get("consequence_version") != 2:
            raise ValueError("Venue change has no audit-time assignment snapshot")
        raw_assignments = details.get("assignments")
        if not isinstance(raw_assignments, list):
            raise ValueError("Venue change has an invalid audit-time assignment snapshot")
        try:
            assignments = tuple(
                VenueAssignment(
                    assignment_id=int(item["assignment_id"]),
                    recipient_member_id=int(item["recipient_member_id"]),
                    committee_id=int(item["committee_id"]),
                )
                for item in raw_assignments
                if isinstance(item, dict)
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "Venue change has an invalid audit-time assignment snapshot"
            ) from error
        if len(assignments) != len(raw_assignments):
            raise ValueError("Venue change has an invalid audit-time assignment snapshot")
        descriptions = describe_venue_change(
            venue_id=audit.venue_id,
            entity_type=audit.entity_type,
            entity_id=audit.entity_id,
            before=details.get("before", {}),
            after=details.get("after", {}),
            changed_fields=frozenset(details.get("changed_fields", ())),
            meaningful_change=details.get("meaningful_change", True),
            assignments=tuple(
                VenueAssignment(
                    assignment_id=item.assignment_id,
                    recipient_member_id=item.recipient_member_id,
                    committee_id=item.committee_id,
                )
                for item in assignments
            ),
        )
        return VenueAuditConsequenceSource(audit, descriptions)

    def is_current(self, consequence_type: str, details: dict, *, today: date) -> bool:
        assignment_ids = tuple(int(value) for value in details["assignment_ids"])
        states = self.repository.assignment_states(assignment_ids)
        fields = (
            calendar_fields_for(details["entity_type"])
            if consequence_type == "calendar"
            else notification_fields_for(details["entity_type"])
        )
        for state in states:
            if not state.confirmed or state.date is None or state.date < today.isoformat():
                continue
            if details["entity_type"] == "room":
                if state.room_id != details["entity_id"] or state.room_values is None:
                    continue
                values = state.room_values
            else:
                venue_id = details.get("venue_id", details["entity_id"])
                if state.venue_id != venue_id or state.venue_values is None:
                    continue
                values = state.venue_values
            if signature(dict(values), fields) == details["expected_signature"]:
                return True
        return False


def describe_venue_change(
    *,
    venue_id: int,
    entity_type: str,
    entity_id: int,
    before: dict,
    after: dict,
    changed_fields: frozenset[str],
    meaningful_change: bool,
    assignments: tuple[VenueAssignment, ...],
) -> VenueConsequenceDescriptions:
    """Derive independent calendar and notification effects from detached values."""
    calendar_fields = changed_fields & calendar_fields_for(entity_type)
    notification_fields = changed_fields & notification_fields_for(entity_type)
    if not meaningful_change:
        notification_fields = frozenset()
    calendar_signature = signature(after, calendar_fields_for(entity_type))
    notification_signature = signature(after, notification_fields_for(entity_type))

    calendar = tuple(
        VenueCalendarConsequence(
            recipient_member_id=assignment.recipient_member_id,
            assignment_id=assignment.assignment_id,
            entity_type=entity_type,
            entity_id=entity_id,
            expected_signature=tuple(sorted(calendar_signature.items())),
        )
        for assignment in assignments
        if calendar_fields
    )
    by_recipient: dict[tuple[int, int], list[int]] = {}
    for assignment in assignments:
        by_recipient.setdefault(
            (assignment.recipient_member_id, assignment.committee_id), []
        ).append(assignment.assignment_id)
    labels = labels_for(notification_fields)
    notifications = tuple(
        VenueNotificationConsequence(
            recipient_member_id=member_id,
            assignment_ids=tuple(sorted(assignment_ids)),
            committee_id=committee_id,
            venue_id=venue_id,
            entity_type=entity_type,
            entity_id=entity_id,
            expected_signature=tuple(sorted(notification_signature.items())),
            fields=labels,
        )
        for (member_id, committee_id), assignment_ids in sorted(by_recipient.items())
        if notification_fields
    )
    return VenueConsequenceDescriptions(
        calendar=calendar,
        notifications=notifications,
        calendar_fields=labels_for(calendar_fields),
        notification_fields=labels,
    )


def calendar_fields_for(entity_type: str) -> frozenset[str]:
    return CALENDAR_ROOM_FIELDS if entity_type == "room" else CALENDAR_VENUE_FIELDS


def notification_fields_for(entity_type: str) -> frozenset[str]:
    return NOTIFICATION_ROOM_FIELDS if entity_type == "room" else NOTIFICATION_VENUE_FIELDS


def signature(values: dict, fields: frozenset[str]) -> dict[str, object]:
    return {field: values.get(field) for field in sorted(fields)}


def labels_for(fields: frozenset[str]) -> tuple[str, ...]:
    return tuple(sorted({FIELD_LABELS[field] for field in fields}))
