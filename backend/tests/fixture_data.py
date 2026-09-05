"""Test-only view of the canonical fixture JSON."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from fixtures.generate import ENTITY_GROUPS, demo_roles, load_source, runtime_profile

DATA = load_source()
FIXTURE_ROOT = DATA["fixture_root"]
FIXTURE_CATALOG_VERSION = DATA["version"]
FIXTURE_CATALOG_REVISION = DATA["revision"]
DEMO_MATRIX_VERSION = DATA["demo_matrix_version"]
FIXTURE_PROFILES = DATA["profiles"]
DEMO_ROLES = demo_roles(DATA)

FIXTURE_IDS = {}
for group in ENTITY_GROUPS:
    for row in DATA[group]:
        value = {"entity_type": group}
        if "id" in row:
            value["id"] = row["id"]
        FIXTURE_IDS[row["fixture_key"]] = value

DISPLAY_NAMES = {}
for group in ("persons", "committees", "locations", "rooms"):
    for row in DATA[group]:
        if group == "persons":
            display_name = f"{row['first_name']} {row['last_name']}"
        else:
            display_name = row["name"]
        DISPLAY_NAMES[row["fixture_key"]] = display_name

ORGANIZATION_NAMES = {row["fixture_key"]: row["name"] for row in DATA["organizations"]}
CANDIDATE_EXAM_NUMBERS = {row["fixture_key"]: row["ihk_exam_number"] for row in DATA["candidates"]}
ADAPTER_COUNTS = {
    adapter: {
        group: len([row for row in DATA[group] if adapter in row.get("adapters", ())])
        for group in (
            "committees",
            "memberships",
            "locations",
            "rooms",
            "location_contacts",
            "candidates",
        )
    }
    for adapter in ("seed", "frontend")
}

PUBLIC_DEMO_RUNTIME = runtime_profile(DATA, "public-demo")
ROUND_ID = PUBLIC_DEMO_RUNTIME["round_id"]
ABSENCE_DAY_ID = PUBLIC_DEMO_RUNTIME["absence"]["day_id"]
ABSENCE_ASSIGNMENT_ID = PUBLIC_DEMO_RUNTIME["absence"]["assignment_id"]
PLAN_CHANGE_DAY_ID = PUBLIC_DEMO_RUNTIME["plan_change"]["day_id"]
PLAN_CHANGE_ASSIGNMENT_ID = PUBLIC_DEMO_RUNTIME["plan_change"]["assignment_id"]
PLAN_REPLACEMENT_MEMBER_ID = PUBLIC_DEMO_RUNTIME["plan_change"]["replacement_member_id"]
REPLACEMENT_MEMBER_ID = PUBLIC_DEMO_RUNTIME["roles"]["replacement"]["committee_member_id"]
SOURCE_LOCATION_ID = PUBLIC_DEMO_RUNTIME["plan_change"]["source_location_id"]
TARGET_LOCATION_ID = PUBLIC_DEMO_RUNTIME["plan_change"]["target_location_id"]
PLAN_CHANGE_REASON = PUBLIC_DEMO_RUNTIME["plan_change"]["reason"]
ABSENCE_ASSIGNMENT_START_ID = ABSENCE_ASSIGNMENT_ID - 1
PLAN_CHANGE_ASSIGNMENT_START_ID = PLAN_CHANGE_ASSIGNMENT_ID - 1
TIME_ZONE = ZoneInfo("Europe/Berlin")


def _closest_relative_exam_date(current: datetime):
    local_now = current.astimezone(TIME_ZONE)
    candidates = [local_now.date() + timedelta(days=days) for days in (1, 2)]
    return min(candidates, key=lambda candidate: abs((candidate - local_now.date()).days - 1))


def seed_demo_scenarios(db_path, created_at: datetime) -> None:
    """Rebuild a test database from the public profile at a chosen reference time."""
    from backend.database import initialize
    from fixtures.generate import render_profile_sql

    initialize(
        db_path,
        seed_sql=render_profile_sql(
            DATA, "public-demo", reference_time=created_at.astimezone(UTC).isoformat()
        ),
        reset=True,
    )


def public_demo_seed_sql() -> str:
    from fixtures.generate import render_profile_sql

    return render_profile_sql(
        DATA,
        "public-demo",
        reference_time=datetime.now(UTC).replace(microsecond=0).isoformat(),
    )


def prepare_exam_protocol_scenario(db_path) -> None:
    """Prepare the complete development profile for protocol/lifecycle tests."""
    from backend.database import initialize
    from fixtures.generate import render_profile_sql

    initialize(db_path, seed_sql=render_profile_sql(DATA, "development"), reset=True)
