from __future__ import annotations

from typing import Any

from .models import Resource
from .repositories import REST_RESOURCES
from .version import application_version, build_revision

RELATED_RESOURCE_FIELDS = {
    "committee_id": "committees",
    "exam_half_year_id": "exam-half-years",
    "created_by_member_id": "members",
    "updated_by_member_id": "members",
    "committee_member_id": "members",
    "default_room_id": "exam-rooms",
    "venue_id": "exam-venues",
    "room_id": "exam-rooms",
    "exam_round_id": "exam-rounds",
    "candidate_id": "candidates",
    "candidate_exam_day_id": "candidate-exam-days",
    "exam_day_id": "exam-days",
    "round_candidate_id": "round-candidates",
}


def api_root() -> dict[str, Any]:
    return {
        "name": "lzug API",
        "version": application_version(),
        "_links": {
            "self": {"href": "/api"},
            "health": {"href": "/api/health"},
            "readiness": {"href": "/api/ready"},
            "openapi": {"href": "/api/openapi.json"},
            "docs": {"href": "/api/docs"},
            "round-summary": {"href": "/api/round-summary?round_id=1"},
            "confirmed-plans": {"href": "/api/confirmed-plans"},
            "notifications": {"href": "/api/notifications"},
            "absence-reports": {"href": "/api/absence-reports"},
            "notification-overview": {"href": "/api/notification-overview"},
            "notification-channels": {"href": "/api/notification-channels"},
            "planning-proposals": {
                "href": "/api/planning-proposals",
                "method": "POST",
            },
            "generate-candidate-exam-days": {
                "href": "/api/candidate-exam-days/generate",
                "method": "POST",
            },
            "confirm-plan": {
                "href": "/api/exam-rounds/1/confirm-plan",
                "method": "POST",
            },
            "candidate-committee-assignments": {"href": "/api/candidate-committee-assignments"},
            **{
                resource_name: {"href": f"/api/{resource_name}"} for resource_name in REST_RESOURCES
            },
        },
    }


def health(status: str, signal: str = "health") -> dict[str, Any]:
    """Expose one minimal public health signal without infrastructure details."""
    if signal not in {"health", "ready"}:
        raise ValueError("Unknown health signal")
    return {
        "status": status,
        "version": application_version(),
        "revision": build_revision(),
        "_links": {
            "self": {"href": f"/api/{signal}"},
        },
    }


def collection(
    resource_name: str,
    resource: Resource,
    rows: list[dict[str, Any]],
    query_string: str = "",
    allow_create: bool = True,
    allow_item_mutation: bool = True,
) -> dict[str, Any]:
    href = f"/api/{resource_name}"
    if query_string:
        href = f"{href}?{query_string}"
    links = {
        "self": {"href": href},
        "api": {"href": "/api"},
    }
    if allow_create:
        links["create"] = {"href": f"/api/{resource_name}", "method": "POST"}
    return {
        "items": [
            resource_item(resource_name, resource, row, allow_item_mutation=allow_item_mutation)
            for row in rows
        ],
        "_links": links,
    }


def resource_item(
    resource_name: str,
    resource: Resource,
    row: dict[str, Any],
    allow_item_mutation: bool = True,
) -> dict[str, Any]:
    item = _legacy_room_reference(resource_name, row)
    item["_links"] = item_links(resource_name, resource, row, allow_item_mutation)
    return item


def exam_venue_collection(venues: list[dict[str, Any]]) -> dict[str, Any]:
    """Link the dedicated venue aggregate without routing it through generic CRUD."""
    return {
        "items": [exam_venue(venue) for venue in venues],
        "_links": {
            "self": {"href": "/api/exam-venues"},
            "api": {"href": "/api"},
            "create": {"href": "/api/exam-venues", "method": "POST"},
        },
    }


def exam_venue(venue: dict[str, Any]) -> dict[str, Any]:
    """Represent venue, rooms, and contacts as one revisioned aggregate."""
    venue_id = venue["id"]
    return {
        **venue,
        "rooms": [exam_room(room) for room in venue["rooms"]],
        "contacts": [exam_venue_contact(contact) for contact in venue["contacts"]],
        "_links": {
            "self": {"href": f"/api/exam-venues/{venue_id}"},
            "collection": {"href": "/api/exam-venues"},
            "update": {"href": f"/api/exam-venues/{venue_id}", "method": "PATCH"},
            "delete": {"href": f"/api/exam-venues/{venue_id}", "method": "DELETE"},
            "rooms": {"href": f"/api/exam-venues/{venue_id}/rooms", "method": "POST"},
            "contacts": {"href": f"/api/exam-venues/{venue_id}/contacts", "method": "POST"},
        },
    }


def exam_room(room: dict[str, Any]) -> dict[str, Any]:
    """Link one room to its venue while keeping its own revision contract visible."""
    room_id = room["id"]
    venue_id = room["venue_id"]
    return {
        **room,
        "_links": {
            "self": {"href": f"/api/exam-rooms/{room_id}"},
            "venue": {"href": f"/api/exam-venues/{venue_id}"},
            "update": {"href": f"/api/exam-rooms/{room_id}", "method": "PATCH"},
            "delete": {"href": f"/api/exam-rooms/{room_id}", "method": "DELETE"},
        },
    }


def exam_venue_contact(contact: dict[str, Any]) -> dict[str, Any]:
    """Link contact master data without treating it as an authenticated identity."""
    contact_id = contact["id"]
    venue_id = contact["venue_id"]
    return {
        **contact,
        "_links": {
            "self": {"href": f"/api/exam-venue-contacts/{contact_id}"},
            "venue": {"href": f"/api/exam-venues/{venue_id}"},
            "update": {"href": f"/api/exam-venue-contacts/{contact_id}", "method": "PATCH"},
            "delete": {"href": f"/api/exam-venue-contacts/{contact_id}", "method": "DELETE"},
        },
    }


def legacy_location_collection(locations: list[dict[str, Any]]) -> dict[str, Any]:
    """Expose a read-only compatibility shape until the client uses venue aggregates."""
    return {
        "items": [legacy_location(location) for location in locations],
        "_links": {"self": {"href": "/api/locations"}, "api": {"href": "/api"}},
    }


def legacy_location(location: dict[str, Any]) -> dict[str, Any]:
    """Link the deprecated location projection back to its canonical venue."""
    return {
        **location,
        "_links": {
            "self": {"href": f"/api/locations/{location['id']}"},
            "venue": {"href": f"/api/exam-venues/{location['venue_id']}"},
        },
    }


def _legacy_room_reference(resource_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """Keep the pre-#587 client readable while exposing canonical room fields."""
    item = dict(row)
    aliases = {
        "planning-settings": ("default_room_id", "default_location_id"),
        "exam-days": ("room_id", "location_id"),
    }
    canonical, legacy = aliases.get(resource_name, (None, None))
    if canonical is not None and legacy is not None and canonical in item:
        item[legacy] = item[canonical]
    return item


def _legacy_proposal_room_references(proposal: dict[str, Any]) -> dict[str, Any]:
    """Expose a temporary location alias without changing persisted plan payloads."""
    linked = dict(proposal)
    days = proposal.get("exam_days")
    if isinstance(days, list):
        linked["exam_days"] = [
            (
                {
                    **day,
                    **({"location_id": day["room_id"]} if "room_id" in day else {}),
                }
                if isinstance(day, dict)
                else day
            )
            for day in days
        ]
    return linked


def item_links(
    resource_name: str,
    resource: Resource,
    row: dict[str, Any],
    allow_item_mutation: bool = True,
) -> dict[str, Any]:
    resource_id = row["id"]
    links = {
        "self": {"href": f"/api/{resource_name}/{resource_id}"},
        "collection": {"href": f"/api/{resource_name}"},
    }
    if allow_item_mutation:
        links["update"] = {"href": f"/api/{resource_name}/{resource_id}", "method": "PATCH"}
        links["delete"] = {"href": f"/api/{resource_name}/{resource_id}", "method": "DELETE"}
    for field, related_resource in RELATED_RESOURCE_FIELDS.items():
        related_id = row.get(field)
        if related_id is not None and field in resource.readable_fields:
            relation = field.removesuffix("_id")
            links[relation] = {"href": f"/api/{related_resource}/{related_id}"}
    return links


def round_summary(summary: dict[str, Any], round_id: int) -> dict[str, Any]:
    linked = dict(summary)
    settings = summary.get("settings")
    if isinstance(settings, dict):
        linked["settings"] = _legacy_room_reference("planning-settings", settings)
    linked["_links"] = {
        "self": {"href": f"/api/round-summary?round_id={round_id}"},
        "api": {"href": "/api"},
        "round": {"href": f"/api/exam-rounds/{round_id}"},
        "candidates": {"href": "/api/candidates"},
        "planning-settings": {"href": f"/api/planning-settings?round_id={round_id}"},
        "candidate-exam-days": {"href": f"/api/candidate-exam-days?round_id={round_id}"},
        "member-availabilities": {"href": f"/api/member-availabilities?round_id={round_id}"},
        "exam-half-years": {"href": "/api/exam-half-years"},
    }
    return linked


def scheduling_overview(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": [
            {
                **item,
                "_links": {
                    "self": {"href": f"/api/exam-rounds/{item['id']}"},
                    "planning": {"href": f"/api/exam-rounds/{item['id']}"},
                },
            }
            for item in items
        ],
        "_links": {
            "self": {"href": "/api/scheduling-overview"},
            "api": {"href": "/api"},
            "exam-rounds": {"href": "/api/exam-rounds"},
        },
    }


def confirmed_plans(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": items,
        "_links": {
            "self": {"href": "/api/confirmed-plans"},
            "api": {"href": "/api"},
        },
    }


def confirmed_plan_day(item: dict[str, Any]) -> dict[str, Any]:
    plan = {
        **item["plan"],
        "exam_half_year": {
            **item["plan"]["exam_half_year"],
            "_links": {
                "self": {"href": f"/api/exam-half-years/{item['plan']['exam_half_year']['id']}"},
                "collection": {"href": "/api/exam-half-years"},
            },
        },
    }
    day = item["day"]
    return {
        **item,
        "plan": plan,
        "_links": {
            "self": {"href": f"/api/confirmed-plan-days/{day['id']}"},
            "api": {"href": "/api"},
            "confirmed-plan": {"href": "/api/confirmed-plans"},
            "round": {"href": f"/api/exam-rounds/{plan['id']}"},
        },
    }


def planning_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    round_id = proposal["round_id"]
    linked = _legacy_proposal_room_references(proposal)
    linked["_links"] = {
        "self": {"href": "/api/planning-proposals", "method": "POST"},
        "api": {"href": "/api"},
        "round": {"href": f"/api/exam-rounds/{round_id}"},
        "round-summary": {"href": f"/api/round-summary?round_id={round_id}"},
        "exam-days": {"href": f"/api/exam-days?round_id={round_id}"},
        "exam-slots": {"href": "/api/exam-slots"},
        "exam-day-assignments": {"href": "/api/exam-day-assignments"},
        "confirm-plan": {
            "href": f"/api/exam-rounds/{round_id}/confirm-plan",
            "method": "POST",
        },
    }
    return linked


def editable_planning_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    """Link one complete, revisioned proposal at its aggregate resource."""
    round_id = proposal["round_id"]
    linked = _legacy_proposal_room_references(proposal)
    linked["_links"] = {
        "self": {
            "href": f"/api/exam-rounds/{round_id}/planning-proposal",
        },
        "update": {
            "href": f"/api/exam-rounds/{round_id}/planning-proposal",
            "method": "PUT",
        },
        "confirm-plan": {
            "href": f"/api/exam-rounds/{round_id}/confirm-plan",
            "method": "POST",
        },
        "round": {"href": f"/api/exam-rounds/{round_id}"},
        "api": {"href": "/api"},
    }
    return linked


def editable_confirmed_plan(
    proposal: dict[str, Any],
    *,
    latest_revision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Link the controlled aggregate for revising a confirmed plan."""
    round_id = proposal["round_id"]
    linked = _legacy_proposal_room_references(proposal)
    if latest_revision is not None:
        linked["latest_revision"] = latest_revision
    linked["_links"] = {
        "self": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan"},
        "update": {
            "href": f"/api/exam-rounds/{round_id}/confirmed-plan",
            "method": "PUT",
        },
        "revisions": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan/revisions"},
        "consequences": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan/consequences"},
        "round": {"href": f"/api/exam-rounds/{round_id}"},
        "api": {"href": "/api"},
    }
    return linked


def confirmed_plan_revisions(
    round_id: int,
    revisions: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "items": revisions,
        "_links": {
            "self": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan/revisions"},
            "confirmed-plan": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan"},
            "round": {"href": f"/api/exam-rounds/{round_id}"},
            "api": {"href": "/api"},
        },
    }


def plan_consequences(round_id: int, consequences: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "items": consequences,
        "_links": {
            "self": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan/consequences"},
            "confirmed-plan": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan"},
            "revisions": {"href": f"/api/exam-rounds/{round_id}/confirmed-plan/revisions"},
            "api": {"href": "/api"},
        },
    }


def confirmed_plan(result: dict[str, Any]) -> dict[str, Any]:
    round_id = result["round_id"]
    linked = _legacy_proposal_room_references(result)
    linked["_links"] = {
        "self": {
            "href": f"/api/exam-rounds/{round_id}/confirm-plan",
            "method": "POST",
        },
        "api": {"href": "/api"},
        "round": {"href": f"/api/exam-rounds/{round_id}"},
        "round-summary": {"href": f"/api/round-summary?round_id={round_id}"},
        "exam-days": {"href": f"/api/exam-days?round_id={round_id}"},
        "exam-slots": {"href": "/api/exam-slots"},
        "exam-day-assignments": {"href": "/api/exam-day-assignments"},
    }
    return linked


def candidate_day_generation(result: dict[str, Any]) -> dict[str, Any]:
    round_id = result["round_id"]
    linked = dict(result)
    linked["_links"] = {
        "self": {"href": "/api/candidate-exam-days/generate", "method": "POST"},
        "api": {"href": "/api"},
        "round": {"href": f"/api/exam-rounds/{round_id}"},
        "planning-settings": {"href": f"/api/planning-settings?round_id={round_id}"},
        "candidate-exam-days": {"href": f"/api/candidate-exam-days?round_id={round_id}"},
    }
    return linked
