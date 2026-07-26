from __future__ import annotations

from typing import Any

from .models import Resource
from .repositories import REST_RESOURCES

RELATED_RESOURCE_FIELDS = {
    "committee_id": "committees",
    "exam_half_year_id": "exam-half-years",
    "created_by_member_id": "members",
    "updated_by_member_id": "members",
    "committee_member_id": "members",
    "default_location_id": "locations",
    "exam_round_id": "exam-rounds",
    "candidate_id": "candidates",
    "candidate_exam_day_id": "candidate-exam-days",
    "exam_day_id": "exam-days",
    "round_candidate_id": "round-candidates",
}


def api_root() -> dict[str, Any]:
    return {
        "name": "lzug API",
        "_links": {
            "self": {"href": "/api"},
            "health": {"href": "/api/health"},
            "openapi": {"href": "/api/openapi.json"},
            "docs": {"href": "/api/docs"},
            "round-summary": {"href": "/api/round-summary?round_id=1"},
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


def health(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "_links": {
            "self": {"href": "/api/health"},
            "api": {"href": "/api"},
            "openapi": {"href": "/api/openapi.json"},
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
    item = dict(row)
    item["_links"] = item_links(resource_name, resource, row, allow_item_mutation)
    return item


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


def planning_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    round_id = proposal["round_id"]
    linked = dict(proposal)
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


def confirmed_plan(result: dict[str, Any]) -> dict[str, Any]:
    round_id = result["round_id"]
    linked = dict(result)
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
