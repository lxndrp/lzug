#!/usr/bin/env python3
"""Generate layer-specific fixture adapters from the canonical synthetic data."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "synthetic-fixtures.json"
SQL_TARGET = ROOT / "db" / "seed_demo.sql"
DEVELOPMENT_SQL_TARGET = ROOT / "db" / "seed_development.sql"
PUBLIC_DEMO_SQL_TARGET = ROOT / "db" / "seed_public_demo.sql"
PUBLIC_DEMO_PROFILE_SQL = ROOT / "fixtures" / "profiles" / "public-demo.sql"
TYPESCRIPT_TARGET = (
    ROOT / "frontend" / "src" / "app" / "testing" / "synthetic-fixtures.generated.ts"
)
PYTHON_TARGET = ROOT / "demo" / "synthetic_fixtures_generated.py"

FIXTURE_ROOT = "name.papaspyrou.repertoire.lzug.fixture"
ENTITY_GROUPS = (
    "organizations",
    "committees",
    "persons",
    "memberships",
    "accounts",
    "locations",
    "rooms",
    "location_contacts",
    "candidates",
)
ACTIVE_ADAPTERS = frozenset({"seed", "frontend"})
PROFILE_NAMES = ("development", "public-demo")
FIXTURE_KEY_PATTERN = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
SOURCE_RETRIEVED_AT = "2026-09-01"
REQUIRED_COVERAGE = {
    "chair",
    "deputy_chair",
    "representing_side_employer",
    "representing_side_employee",
    "representing_side_school",
    "ordinary_member",
    "deputy_member",
    "fallback",
    "replacement",
    "cross_committee",
    "candidates",
    "foreign_committee",
    "suitable_staffing",
    "unsuitable_staffing",
    "positive_authorization",
    "negative_authorization",
    "demo_487_absence",
    "demo_487_planchange",
}

SPECIALIZATION_LABELS = {
    "application_development": "Anwendungsentwicklung",
    "system_integration": "Systemintegration",
    "data_and_process_analysis": "Daten- und Prozessanalyse",
    "digital_networking": "Digitale Vernetzung",
}
MEMBER_STATUS_LABELS = {
    "ordinary": "Ordentliches Mitglied",
    "deputy": "Stellvertretendes Mitglied",
}
COMMITTEE_ROLE_LABELS = {
    "chair": "Vorsitz",
    "deputy_chair": "Stellvertretender Vorsitz",
    "member": "Mitglied",
}
REPRESENTING_SIDE_LABELS = {
    "employer": "Arbeitgeber",
    "employee": "Arbeitnehmer",
    "school": "Schule",
}


def load_source() -> dict[str, Any]:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


def profiles(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the explicit seed profiles declared beside the entity catalog."""
    declared = data.get("profiles")
    if not isinstance(declared, dict) or set(declared) != set(PROFILE_NAMES):
        raise ValueError("Fixture profiles must declare development and public-demo")
    for name in PROFILE_NAMES:
        profile = declared[name]
        if not isinstance(profile, dict) or profile.get("name") != name:
            raise ValueError(f"Fixture profile is invalid: {name}")
        if not isinstance(profile.get("reference_time"), str):
            raise ValueError(f"Fixture profile has no reference time: {name}")
        if not isinstance(profile.get("scenarios"), list):
            raise ValueError(f"Fixture profile has no scenario declaration: {name}")
    return declared


def adapter_rows(data: dict[str, Any], group: str, adapter: str) -> list[dict[str, Any]]:
    return [row for row in data[group] if adapter in row.get("adapters", ())]


def catalog_index(data: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    index: dict[str, tuple[str, dict[str, Any]]] = {}
    for group in ENTITY_GROUPS:
        for row in data[group]:
            key = row.get("fixture_key")
            if not isinstance(key, str) or not key:
                raise ValueError(f"Fixture key is missing in group: {group}")
            if key in index:
                raise ValueError(f"Duplicate semantic fixture key: {key}")
            index[key] = (group, row)
    return index


def item_by_key(data: dict[str, Any], key: str, group: str) -> dict[str, Any]:
    indexed_group, item = catalog_index(data).get(key, (None, None))
    if indexed_group != group or item is None:
        raise ValueError(f"Unknown {group} fixture key: {key}")
    return item


def resolved_memberships(data: dict[str, Any], adapter: str | None = None) -> list[dict[str, Any]]:
    memberships = data["memberships"]
    if adapter is not None:
        memberships = [row for row in memberships if adapter in row["adapters"]]
    resolved = []
    for membership in memberships:
        person = item_by_key(data, membership["person_key"], "persons")
        committee = item_by_key(data, membership["committee_key"], "committees")
        resolved.append(
            {
                **membership,
                "person_id": person["id"],
                "committee_id": committee["id"],
                "first_name": person["first_name"],
                "last_name": person["last_name"],
                "email": person["email"],
                "mobile": person["mobile"],
            }
        )
    return resolved


def validate_catalog(data: dict[str, Any]) -> None:
    """Fail closed when the canonical fixture catalog is incomplete or unsafe."""
    if data.get("version") != 3 or not data.get("revision"):
        raise ValueError("Unsupported or missing fixture catalog version")
    if data.get("fixture_root") != FIXTURE_ROOT:
        raise ValueError(f"Fixture root must be {FIXTURE_ROOT}")
    if not data.get("demo_matrix_version"):
        raise ValueError("Demo matrix version is required")
    profiles(data)
    for group in ENTITY_GROUPS:
        if not isinstance(data.get(group), list) or not data[group]:
            raise ValueError(f"Fixture group must not be empty: {group}")
        for row in data[group]:
            unknown_adapters = set(row.get("adapters", ())) - ACTIVE_ADAPTERS
            if unknown_adapters:
                raise ValueError(
                    f"Fixture uses unknown adapters: {', '.join(sorted(unknown_adapters))}"
                )

    index = catalog_index(data)
    for key in index:
        if not key.startswith(f"{FIXTURE_ROOT}.") or FIXTURE_KEY_PATTERN.fullmatch(key) is None:
            raise ValueError(f"Fixture key has an invalid root: {key}")

    for group in ENTITY_GROUPS:
        ids = [row["id"] for row in data[group] if "id" in row]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate technical id in fixture group: {group}")

    scenario_keys = {scenario["key"] for scenario in data["scenarios"]}
    if len(scenario_keys) != len(data["scenarios"]):
        raise ValueError("Duplicate scenario key")
    declared_profiles = profiles(data)
    for profile_name, profile in declared_profiles.items():
        scenarios = profile["scenarios"]
        if len(scenarios) != len(set(scenarios)) or not set(scenarios) <= scenario_keys:
            raise ValueError(f"Fixture profile has invalid scenarios: {profile_name}")
    if not {"demo.487.absence", "demo.487.planchange"} <= set(
        declared_profiles["public-demo"]["scenarios"]
    ):
        raise ValueError("Public-demo profile must include both #487 scenarios")
    for _, row in index.values():
        if not row.get("scenarios") and "scenarios" in row:
            raise ValueError(f"Fixture has no scenario coverage: {row['fixture_key']}")
        unknown_scenarios = set(row.get("scenarios", ())) - scenario_keys
        if unknown_scenarios:
            raise ValueError(f"Fixture references unknown scenarios: {row['fixture_key']}")

    for organization in data["organizations"]:
        if (
            organization.get("is_fictional") is not True
            or organization.get("country") != "Griechenland"
            or organization.get("contact") is not None
        ):
            raise ValueError("Organizations must be fictional Greek demo records")

    email_domain = data["conventions"].get("email_domain")
    if email_domain != "demo.lzug.invalid":
        raise ValueError("Synthetic email domain must be demo.lzug.invalid")
    for person in data["persons"]:
        if not person.get("first_name") or not person.get("last_name"):
            raise ValueError("Every synthetic person requires a full name")
        if not person["email"].endswith(f"@{email_domain}"):
            raise ValueError("Synthetic person email uses a forbidden domain")
        if person.get("mobile") is not None:
            raise ValueError("Synthetic person phone numbers are forbidden")
    for candidate in data["candidates"]:
        if not candidate.get("first_name") or not candidate.get("last_name"):
            raise ValueError("Every synthetic candidate requires a full name")
    for account in data["accounts"]:
        if not account["email"].endswith(f"@{email_domain}"):
            raise ValueError("Synthetic account email uses a forbidden domain")
        if account.get("capability_contract") != data["demo_matrix_version"]:
            raise ValueError("Account capability contract does not match demo matrix")

    for committee in data["committees"]:
        item_by_key(data, committee["organization_key"], "organizations")
    for membership in data["memberships"]:
        item_by_key(data, membership["person_key"], "persons")
        item_by_key(data, membership["committee_key"], "committees")
    for account in data["accounts"]:
        item_by_key(data, account["person_key"], "persons")
        membership = item_by_key(data, account["membership_key"], "memberships")
        if membership["person_key"] != account["person_key"]:
            raise ValueError("Demo account and membership reference different people")
    if len(data["locations"]) != 3 or len(data["rooms"]) != 6:
        raise ValueError("The Athens fixture requires exactly three venues and six rooms")
    for location in data["locations"]:
        if location["scope"] == "global":
            if location.get("committee_key") is not None:
                raise ValueError("Global fixture venues must not reference a committee")
        elif location["scope"] == "committee":
            item_by_key(data, location["committee_key"], "committees")
        else:
            raise ValueError("Fixture venue scope must be global or committee")
        coordinates = (location.get("latitude"), location.get("longitude"))
        if (
            location.get("country") != "Greece"
            or location.get("coordinate_status") != "confirmed"
            or not all(isinstance(value, (int, float)) for value in coordinates)
            or not -90 <= coordinates[0] <= 90
            or not -180 <= coordinates[1] <= 180
            or location.get("source_retrieved_at") != SOURCE_RETRIEVED_AT
            or not location.get("reality_notice")
            or not location.get("name", "").endswith("(Demo)")
        ):
            raise ValueError("Athens fixture venue geodata is incomplete or unsafe")
        source_url = urlsplit(location.get("source_url", ""))
        if source_url.scheme != "https" or not source_url.hostname:
            raise ValueError("Fixture venue source URL must be canonical HTTPS")

    rooms_by_venue: dict[str, list[dict[str, Any]]] = {}
    for room in data["rooms"]:
        item_by_key(data, room["venue_key"], "locations")
        rooms_by_venue.setdefault(room["venue_key"], []).append(room)
        if not isinstance(room.get("capacity"), int) or room["capacity"] <= 0:
            raise ValueError("Fixture room capacity must be a positive integer")
        if not room.get("access_notes", "").startswith("Synthetische Auffindung:"):
            raise ValueError("Fixture room access notes must be visibly synthetic")
    if any(
        len(rooms_by_venue.get(location["fixture_key"], ())) != 2 for location in data["locations"]
    ):
        raise ValueError("Every Athens fixture venue requires exactly two rooms")

    contacts_by_venue: dict[str, list[dict[str, Any]]] = {}
    for contact in data["location_contacts"]:
        venue = item_by_key(data, contact["venue_key"], "locations")
        person = item_by_key(data, contact["person_key"], "persons")
        contacts_by_venue.setdefault(contact["venue_key"], []).append(contact)
        if (
            contact["label"] != f"{person['first_name']} {person['last_name']}"
            or contact.get("email") != person["email"]
            or not contact["email"].endswith(f"@{email_domain}")
            or contact.get("phone") is not None
        ):
            raise ValueError("Fixture venue contacts must use synthetic canonical people")
        for room_key in contact.get("room_keys", ()):
            room = item_by_key(data, room_key, "rooms")
            if room["venue_key"] != venue["fixture_key"]:
                raise ValueError("Fixture contact cannot reference a room at another venue")
    expected_contact_counts = {
        f"{FIXTURE_ROOT}.location.global.zappeion": 1,
        f"{FIXTURE_ROOT}.location.committee.athen.gazi": 1,
        f"{FIXTURE_ROOT}.location.committee.feenwald.nationalgarden": 0,
    }
    if any(
        len(contacts_by_venue.get(key, ())) != count
        for key, count in expected_contact_counts.items()
    ):
        raise ValueError("Athens fixture contact cardinalities do not match the demo contract")

    roles = [account["demo_role"] for account in data["accounts"] if account["demo_role"]]
    if sorted(roles) != ["chair", "examiner", "replacement"]:
        raise ValueError("Exactly the three canonical demo roles are required")

    cross_key = f"{FIXTURE_ROOT}.person.crosscommittee"
    cross_committees = {
        membership["committee_key"]
        for membership in data["memberships"]
        if membership["person_key"] == cross_key and membership.get("is_active")
    }
    if len(cross_committees) < 2:
        raise ValueError("Cross-committee fixture must have two active memberships")

    coverage = data.get("coverage_matrix", {})
    if set(coverage) != REQUIRED_COVERAGE:
        raise ValueError("Fixture coverage matrix is incomplete or contains unknown rows")
    for name, keys in coverage.items():
        if not keys or any(key not in index for key in keys):
            raise ValueError(f"Fixture coverage row is invalid: {name}")

    legacy_names = [row["legacy"] for row in data["legacy_mapping"]]
    if len(legacy_names) != len(set(legacy_names)):
        raise ValueError("Legacy fixture mapping is ambiguous")
    for mapping in data["legacy_mapping"]:
        _, target = index.get(mapping["fixture_key"], (None, None))
        if target is None or target.get("id") != mapping["technical_id"]:
            raise ValueError("Legacy fixture mapping does not preserve its technical id")

    validate_seed_committees(data)


def validate_seed_committees(data: dict[str, Any]) -> None:
    """Require every synthetic active committee to have exactly one active chair."""
    committees = adapter_rows(data, "committees", "seed")
    members = resolved_memberships(data, "seed")
    for committee in committees:
        active_chairs = [
            member
            for member in members
            if member["committee_key"] == committee["fixture_key"]
            and member["committee_role"] == "chair"
            and member.get("is_active", 1)
        ]
        if len(active_chairs) != 1:
            raise ValueError(
                f"Synthetic committee {committee['id']} must have exactly one active chair"
            )


def sql_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.6f}"
    return "'" + str(value).replace("'", "''") + "'"


def sql_rows(rows: list[list[Any]]) -> str:
    return ",\n".join("  (" + ", ".join(sql_value(value) for value in row) + ")" for row in rows)


def normalized_seed_text(value: object) -> str:
    """Use the same stable comparison key as the persisted venue model."""
    return " ".join(unicodedata.normalize("NFKC", str(value)).split()).casefold()


def render_sql(data: dict[str, Any], profile: str = "development") -> str:
    committees = adapter_rows(data, "committees", "seed")
    members = resolved_memberships(data, "seed")
    locations = adapter_rows(data, "locations", "seed")
    rooms = adapter_rows(data, "rooms", "seed")
    contacts = adapter_rows(data, "location_contacts", "seed")
    candidates = adapter_rows(data, "candidates", "seed")
    accounts = data["accounts"]
    people = {
        member["person_id"]: item_by_key(data, member["person_key"], "persons")
        for member in members
    }
    committee_rows = [
        [
            row["id"],
            row["name"],
            row["occupation"],
            item_by_key(data, row["organization_key"], "organizations")["name"],
            1,
            "ready",
        ]
        for row in committees
    ]
    person_rows = [
        [
            row["id"],
            row["first_name"],
            row["last_name"],
            row["email"],
            row["mobile"],
        ]
        for row in sorted(people.values(), key=lambda item: item["id"])
    ]
    member_rows = [
        [
            row["id"],
            row["person_id"],
            row["committee_id"],
            row["member_status"],
            row["committee_role"],
            row["representing_side"],
        ]
        for row in members
    ]
    account_rows = [
        [
            row["id"],
            item_by_key(data, row["person_key"], "persons")["id"],
            row["email"],
            "demo-password-hash",
        ]
        for row in accounts
    ]
    venue_rows = [
        [
            row["id"],
            row["scope"],
            (
                item_by_key(data, row["committee_key"], "committees")["id"]
                if row["committee_key"] is not None
                else None
            ),
            row["name"],
            normalized_seed_text(row["name"]),
            row["street"],
            row["postal_code"],
            row["city"],
            row["country"],
            row["site_name"],
            row["entrance"],
            row["travel_directions"],
            row["is_accessible"],
            row["accessibility_status"],
            row["accessibility_notes"],
            row["latitude"],
            row["longitude"],
            row["coordinate_status"],
            row["coordinate_source"],
            0,
        ]
        for row in locations
    ]
    room_rows = [
        [
            row["id"],
            item_by_key(data, row["venue_key"], "locations")["id"],
            row["name"],
            normalized_seed_text(row["name"]),
            row["access_notes"],
            row["capacity"],
            row["is_active"],
        ]
        for row in rooms
    ]
    contact_rows = [
        [
            row["id"],
            item_by_key(data, row["venue_key"], "locations")["id"],
            row["label"],
            row["role"],
            row["phone"],
            row["email"],
            row["availability_notes"],
            row["is_active"],
        ]
        for row in contacts
    ]
    contact_room_rows = [
        [contact["id"], item_by_key(data, room_key, "rooms")["id"]]
        for contact in contacts
        for room_key in contact["room_keys"]
    ]
    candidate_rows = [
        [
            row["id"],
            row["first_name"],
            row["last_name"],
            row["ihk_exam_number"],
            row["specialization"],
            row["training_company"],
        ]
        for row in candidates
    ]
    round_candidate_rows = [
        [
            row["id"],
            1,
            row["id"],
            row["attempt_number"],
            row["requires_mep"],
        ]
        for row in candidates
    ]

    def membership_id(suffix: str) -> int:
        return item_by_key(data, f"{FIXTURE_ROOT}.membership.{suffix}", "memberships")["id"]

    pending_member_ids = ", ".join(
        str(membership_id(suffix)) for suffix in ("examiner.fallback", "examiner.unsuitable")
    )
    afternoon_member_ids = ", ".join(
        str(membership_id(suffix)) for suffix in ("deputy.athen", "examiner.replacement")
    )
    morning_member_ids = ", ".join(
        str(membership_id(suffix)) for suffix in ("examiner.absent", "examiner.reserve")
    )
    contact_room_sql = ""
    if contact_room_rows:
        contact_room_sql = (
            "INSERT INTO exam_venue_contact_room (contact_id, room_id)\nVALUES\n"
            + sql_rows(contact_room_rows)
            + ";\n\n"
        )
    return f"""-- Generated by fixtures/generate.py. Do not edit directly.
-- Fixture profile: {profile}
INSERT INTO committee (id, name, occupation, ihk, is_active, bootstrap_state)
VALUES
{sql_rows(committee_rows)};

INSERT INTO person (id, first_name, last_name, email, mobile)
VALUES
{sql_rows(person_rows)};

INSERT INTO committee_member
  (id, person_id, committee_id, member_status, committee_role, representing_side)
VALUES
{sql_rows(member_rows)};

INSERT INTO user_account (id, person_id, email, password_hash)
VALUES
{sql_rows(account_rows)};

INSERT INTO committee_admin_operation (
  operation_type, committee_id, person_ids_json, membership_ids_json,
  account_ids_json, result, occurred_at, technical_source
)
SELECT
  'legacy_assessment',
  committee.id,
  '[' || COALESCE((
    SELECT group_concat(committee_member.person_id, ',')
    FROM committee_member
    WHERE committee_member.committee_id = committee.id
  ), '') || ']',
  '[' || COALESCE((
    SELECT group_concat(committee_member.id, ',')
    FROM committee_member
    WHERE committee_member.committee_id = committee.id
  ), '') || ']',
  '[' || COALESCE((
    SELECT group_concat(user_account.id, ',')
    FROM user_account
    WHERE user_account.person_id IN (
      SELECT committee_member.person_id
      FROM committee_member
      WHERE committee_member.committee_id = committee.id
    )
  ), '') || ']',
  'ready',
  '2026-01-01T00:00:00+00:00',
  'migration'
FROM committee;

INSERT INTO exam_venue
  (id, scope, committee_id, name, normalized_name, street, postal_code, city,
   country, site_name, entrance, travel_directions, is_accessible,
   accessibility_status, accessibility_notes, latitude, longitude,
   coordinate_status, coordinate_source, is_active)
VALUES
{sql_rows(venue_rows)};

INSERT INTO exam_room
  (id, venue_id, name, normalized_name, access_notes, capacity, is_active)
VALUES
{sql_rows(room_rows)};

UPDATE exam_venue
SET is_active = 1
WHERE id IN ({", ".join(str(row["id"]) for row in locations if row["is_active"])});

INSERT INTO exam_venue_contact
  (id, venue_id, label, role, phone, email, availability_notes, is_active)
VALUES
{sql_rows(contact_rows)};

{contact_room_sql}
INSERT INTO candidate
  (id, first_name, last_name, ihk_exam_number, specialization, training_company)
VALUES
{sql_rows(candidate_rows)};

INSERT INTO exam_half_year (id, season, year, status)
VALUES (1, 'winter', 2026, 'active');

INSERT INTO exam_round
  (id, exam_half_year_id, committee_id, name, status,
   availability_deadline, availability_reminder_at, created_by_member_id)
VALUES
  (1, 1, 1, 'Winter 2026/27', 'availability_requested',
   '2026-10-02 18:00:00', '2026-09-29 18:00:00', 1);

INSERT INTO round_candidate
  (id, exam_round_id, candidate_id, attempt_number, requires_mep)
VALUES
{sql_rows(round_candidate_rows)};

INSERT INTO candidate_committee_assignment
  (candidate_id, exam_half_year_id, exam_round_id, round_candidate_id)
SELECT candidate_id, 1, exam_round_id, id
FROM round_candidate;

INSERT INTO planning_settings
  (id, exam_round_id, calendar_week_from, calendar_week_to, exams_per_day,
   max_exam_days_per_week, lunch_break_enabled, default_room_id,
   updated_by_member_id)
VALUES
  (1, 1, '2026-W47', '2026-W49', 6, 3, 1, 1, 1);

INSERT INTO candidate_exam_day (id, exam_round_id, date)
VALUES
  (1, 1, '2026-11-16'),
  (2, 1, '2026-11-17'),
  (3, 1, '2026-11-18'),
  (4, 1, '2026-11-19'),
  (5, 1, '2026-11-20');

INSERT INTO member_availability
  (exam_round_id, committee_member_id, candidate_exam_day_id, availability, responded_at)
SELECT
  1,
  committee_member.id,
  candidate_exam_day.id,
  CASE
    WHEN committee_member.id IN ({pending_member_ids}) THEN 'pending'
    WHEN candidate_exam_day.id = 3
      AND committee_member.id IN ({afternoon_member_ids}) THEN 'afternoon'
    WHEN candidate_exam_day.id = 4
      AND committee_member.id IN ({morning_member_ids}) THEN 'morning'
    ELSE 'full_day'
  END,
  CASE WHEN committee_member.id IN ({pending_member_ids}) THEN NULL ELSE CURRENT_TIMESTAMP END
FROM committee_member
CROSS JOIN candidate_exam_day
WHERE committee_member.committee_id = 1
  AND candidate_exam_day.exam_round_id = 1;
    """.rstrip() + "\n"


def render_profile_sql(data: dict[str, Any], profile: str) -> str:
    """Compile one complete SQL seed from the catalog and profile declaration."""
    if profile not in PROFILE_NAMES:
        raise ValueError(f"Unknown fixture profile: {profile}")
    content = render_sql(data, profile)
    if profile == "public-demo":
        if not PUBLIC_DEMO_PROFILE_SQL.is_file():
            raise ValueError("Public-demo profile SQL source is missing")
        profile_sql = PUBLIC_DEMO_PROFILE_SQL.read_text(encoding="utf-8").strip()
        content = f"{content.rstrip()}\n\n{profile_sql}\n"
    return content


def render_typescript(data: dict[str, Any]) -> str:
    committees = []
    for row in adapter_rows(data, "committees", "frontend"):
        committees.append(
            {
                "id": row["id"],
                "name": row["name"],
                "occupation": row["occupation"],
                "ihk": item_by_key(data, row["organization_key"], "organizations")["name"],
                "is_active": 1,
                "bootstrap_state": "ready",
            }
        )
    members = []
    for row in resolved_memberships(data, "frontend"):
        members.append(
            {
                "id": row["id"],
                "person_id": row["person_id"],
                "committee_id": row["committee_id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "email": row["email"],
                "mobile": row["mobile"],
                "member_status": row["member_status"],
                "committee_role": row["committee_role"],
                "representing_side": row["representing_side"],
                "is_active": row["is_active"],
                "email_verified_at": None,
            }
        )
    frontend_rooms = adapter_rows(data, "rooms", "frontend")
    locations = []
    for room in frontend_rooms:
        venue = item_by_key(data, room["venue_key"], "locations")
        locations.append(
            {
                "id": room["id"],
                "committee_id": (
                    item_by_key(data, venue["committee_key"], "committees")["id"]
                    if venue["committee_key"] is not None
                    else None
                ),
                "name": venue["name"],
                "street": venue["street"],
                "postal_code": venue["postal_code"],
                "city": venue["city"],
                "room": room["name"],
                "is_active": int(bool(venue["is_active"]) and bool(room["is_active"])),
            }
        )
    exam_venues = []
    for venue in adapter_rows(data, "locations", "frontend"):
        venue_rooms = [room for room in frontend_rooms if room["venue_key"] == venue["fixture_key"]]
        venue_contacts = [
            contact
            for contact in adapter_rows(data, "location_contacts", "frontend")
            if contact["venue_key"] == venue["fixture_key"]
        ]
        exam_venues.append(
            {
                "id": venue["id"],
                "scope": venue["scope"],
                "committee_id": (
                    item_by_key(data, venue["committee_key"], "committees")["id"]
                    if venue["committee_key"] is not None
                    else None
                ),
                **{
                    field: venue[field]
                    for field in (
                        "name",
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
                        "latitude",
                        "longitude",
                        "coordinate_status",
                        "coordinate_source",
                        "is_active",
                    )
                },
                "revision": 1,
                "rooms": [
                    {
                        "id": room["id"],
                        "venue_id": venue["id"],
                        "name": room["name"],
                        "building": None,
                        "wing": None,
                        "floor": None,
                        "room_number": None,
                        "access_notes": room["access_notes"],
                        "capacity": room["capacity"],
                        "is_active": room["is_active"],
                        "revision": 1,
                        "_links": {},
                    }
                    for room in venue_rooms
                ],
                "contacts": [
                    {
                        "id": contact["id"],
                        "venue_id": venue["id"],
                        "label": contact["label"],
                        "role": contact["role"],
                        "phone": contact["phone"],
                        "email": contact["email"],
                        "availability_notes": contact["availability_notes"],
                        "is_active": contact["is_active"],
                        "revision": 1,
                        "room_ids": [
                            item_by_key(data, room_key, "rooms")["id"]
                            for room_key in contact["room_keys"]
                        ],
                        "_links": {},
                    }
                    for contact in venue_contacts
                ],
                "map_provider": {
                    "mode": "osm",
                    "attribution": "© OpenStreetMap-Mitwirkende",
                    "attribution_url": "https://www.openstreetmap.org/copyright",
                },
                "capabilities": {
                    "manage": False,
                    "request_promotion": False,
                    "decide_promotion": False,
                },
                "_links": {},
            }
        )
    candidates = []
    for row in adapter_rows(data, "candidates", "frontend"):
        candidates.append(
            {
                "id": row["id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "ihk_exam_number": row["ihk_exam_number"],
                "specialization": SPECIALIZATION_LABELS[row["specialization"]],
                "training_company": row["training_company"],
            }
        )
    payload = {
        "version": data["version"],
        "revision": data["revision"],
        "fixtureRoot": data["fixture_root"],
        "demoMatrixVersion": data["demo_matrix_version"],
        "keys": {
            group: {row["fixture_key"]: row["id"] for row in data[group] if "id" in row}
            for group in ENTITY_GROUPS
        },
        "demoRoles": demo_roles(data),
        "committees": committees,
        "members": members,
        "locations": locations,
        "examVenues": exam_venues,
        "candidates": candidates,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    return (
        "// Generated by fixtures/generate.py. Do not edit directly.\n"
        f"export const syntheticFixtures = {content} as const;\n"
    )


def demo_roles(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    roles = {}
    for account in data["accounts"]:
        if not account["demo_role"]:
            continue
        person = item_by_key(data, account["person_key"], "persons")
        membership = item_by_key(data, account["membership_key"], "memberships")
        roles[account["demo_role"]] = {
            "account_id": account["id"],
            "person_id": person["id"],
            "committee_member_id": membership["id"],
            "first_name": person["first_name"],
            "last_name": person["last_name"],
            "display_name": f"{person['first_name']} {person['last_name']}",
            "account_email": account["email"],
            "person_email": person["email"],
            "fixture_key": person["fixture_key"],
        }
    return roles


def render_python(data: dict[str, Any]) -> str:
    fixture_ids = {
        row["fixture_key"]: {
            "entity_type": group,
            **({"id": row["id"]} if "id" in row else {}),
        }
        for group in ENTITY_GROUPS
        for row in data[group]
    }

    def json_assignment(name: str, value: Any) -> str:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        return f'{name} = json.loads(r"""{payload}""")\n'

    organizations = {row["fixture_key"]: row["name"] for row in data["organizations"]}
    display_names = {
        row["fixture_key"]: (
            row["name"] if "name" in row else f"{row['first_name']} {row['last_name']}"
        )
        for group in ENTITY_GROUPS
        for row in data[group]
        if "name" in row or ("first_name" in row and "last_name" in row)
    }
    candidate_exam_numbers = {
        row["fixture_key"]: row["ihk_exam_number"] for row in data["candidates"]
    }
    adapter_names = sorted(ACTIVE_ADAPTERS)
    adapter_counts = {
        adapter: {group: len(adapter_rows(data, group, adapter)) for group in ENTITY_GROUPS}
        for adapter in adapter_names
    }
    return (
        '"""Generated semantic identities for the public demo. Do not edit directly."""\n\n'
        "# ruff: noqa: E501\n\n"
        "import json\n\n"
        f"FIXTURE_CATALOG_VERSION = {data['version']}\n"
        f"FIXTURE_CATALOG_REVISION = {json.dumps(data['revision'])}\n"
        f"FIXTURE_ROOT = {json.dumps(data['fixture_root'])}\n"
        f"DEMO_MATRIX_VERSION = {json.dumps(data['demo_matrix_version'])}\n\n"
        + json_assignment("FIXTURE_PROFILES", profiles(data))
        + "\n"
        + json_assignment("FIXTURE_IDS", fixture_ids)
        + "\n"
        + json_assignment("ORGANIZATION_NAMES", organizations)
        + "\n"
        + json_assignment("DISPLAY_NAMES", display_names)
        + "\n"
        + json_assignment("CANDIDATE_EXAM_NUMBERS", candidate_exam_numbers)
        + "\n"
        + json_assignment("ADAPTER_COUNTS", adapter_counts)
        + "\n"
        + json_assignment("DEMO_ROLES", demo_roles(data))
    )


def outputs(data: dict[str, Any], profile: str | None = None) -> dict[Path, str]:
    validate_catalog(data)
    if profile is not None and profile not in PROFILE_NAMES:
        raise ValueError(f"Unknown fixture profile: {profile}")
    generated = {
        SQL_TARGET: render_sql(data, "development"),
        DEVELOPMENT_SQL_TARGET: render_sql(data, "development"),
        TYPESCRIPT_TARGET: render_typescript(data),
        PYTHON_TARGET: render_python(data),
    }
    if profile is None or profile == "public-demo":
        generated[PUBLIC_DEMO_SQL_TARGET] = render_profile_sql(data, "public-demo")
    return generated


def generate(check: bool = False, profile: str | None = None) -> list[Path]:
    mismatches = []
    for path, content in outputs(load_source(), profile).items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated adapters do not match the canonical source",
    )
    parser.add_argument("--profile", choices=PROFILE_NAMES)
    args = parser.parse_args()
    mismatches = generate(check=args.check, profile=args.profile)
    if mismatches:
        for path in mismatches:
            print(f"outdated synthetic fixture adapter: {path.relative_to(ROOT)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
