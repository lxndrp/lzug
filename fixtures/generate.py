#!/usr/bin/env python3
"""Compile disposable fixture seeds and tracked adapters from canonical data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "fixtures" / "synthetic-fixtures.json"
TYPESCRIPT_TARGET = (
    ROOT / "frontend" / "src" / "app" / "testing" / "synthetic-fixtures.generated.ts"
)

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
        records = profile.get("seed_records", [])
        if not isinstance(records, list):
            raise ValueError(f"Fixture profile has invalid seed records: {name}")
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


def _shift_reference_value(value: Any, reference_time: str) -> Any:
    if not isinstance(value, str):
        return value
    if value == "@reference_time":
        return reference_time
    target = datetime.fromisoformat(reference_time)
    canonical = datetime(2026, 1, 1, tzinfo=UTC)
    local_zone = ZoneInfo("Europe/Berlin")
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            shifted = date.fromisoformat(value) + (
                target.astimezone(local_zone).date() - canonical.astimezone(local_zone).date()
            )
            return shifted.isoformat()
        if "T" in value:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            shifted = parsed.astimezone(UTC) + (target.astimezone(UTC) - canonical)
            return shifted.isoformat(timespec="seconds")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
            parsed = datetime.fromisoformat(value)
            shifted_date = parsed.date() + (
                target.astimezone(local_zone).date() - canonical.astimezone(local_zone).date()
            )
            return datetime.combine(shifted_date, parsed.time()).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        pass
    return value


def _seed_records(
    data: dict[str, Any],
    profile: str,
    *,
    excluded_ids: dict[str, set[Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    declared = profiles(data)[profile]
    common_records = list(data.get("seed_records", []))
    profile_records = list(declared.get("seed_records", []))
    # The public profile deliberately overrides the generic development base
    # for shared technical ids (for example the prepared demo round).
    source_records = (
        profile_records + common_records
        if profile == "public-demo"
        else common_records + profile_records
    )
    seen_ids: dict[str, set[Any]] = {}
    records = []
    excluded_ids = excluded_ids or {}
    for record in source_records:
        table = record["table"]
        columns = record["columns"]
        id_index = columns.index("id") if "id" in columns else None
        filtered_rows = []
        for row in record["rows"]:
            row_id = row[id_index] if id_index is not None else None
            if row_id is not None and row_id in excluded_ids.get(table, set()):
                continue
            if row_id is not None and row_id in seen_ids.setdefault(table, set()):
                continue
            if row_id is not None:
                seen_ids.setdefault(table, set()).add(row_id)
            filtered_rows.append(row)
        if filtered_rows:
            records.append({**record, "rows": filtered_rows})
    replace_tables = list(declared.get("replace_tables", []))
    return records, replace_tables


def _render_record_set(record: dict[str, Any], reference_time: str) -> str:
    table = record.get("table")
    columns = record.get("columns")
    rows = record.get("rows")
    if (
        not isinstance(table, str)
        or re.fullmatch(r"[a-z_]+", table) is None
        or not isinstance(columns, list)
        or not columns
        or not all(
            isinstance(column, str) and re.fullmatch(r"[a-z_]+", column) for column in columns
        )
        or not isinstance(rows, list)
    ):
        raise ValueError(f"Invalid declarative seed record: {table!r}")
    if any(len(row) != len(columns) for row in rows):
        raise ValueError(f"Seed record row does not match columns: {table}")
    resolved_rows = [
        [_shift_reference_value(value, reference_time) for value in row] for row in rows
    ]
    if table == "calendar_event" and "content_hash" in columns:
        content_index = columns.index("content_hash")
        payload_columns = {
            "exam_half_year_id",
            "exam_round_id",
            "exam_day_id",
            "exam_day_assignment_id",
            "recipient_member_id",
            "date",
            "starts_at",
            "ends_at",
            "time_zone",
            "location",
            "role",
            "round_name",
            "secure_reference",
            "source_key",
            "status",
            "sent_at",
        }
        for row in resolved_rows:
            payload = {
                column: value
                for column, value in zip(columns, row, strict=True)
                if column in payload_columns and column != "sent_at"
            }
            row[content_index] = hashlib.sha256(
                repr(sorted(payload.items())).encode("utf-8")
            ).hexdigest()
    return f'INSERT INTO "{table}" ({", ".join(columns)}) VALUES\n' f"{sql_rows(resolved_rows)};"


def render_seed_records(
    data: dict[str, Any],
    profile: str,
    *,
    excluded_ids: dict[str, set[Any]] | None = None,
    reference_time: str | None = None,
) -> str:
    records, replace_tables = _seed_records(data, profile, excluded_ids=excluded_ids)
    reference_time = reference_time or profiles(data)[profile]["reference_time"]
    statements = ["PRAGMA foreign_keys = OFF;", "PRAGMA defer_foreign_keys = ON;"]
    statements.extend(f'DELETE FROM "{table}";' for table in replace_tables)
    statements.extend(_render_record_set(record, reference_time) for record in records)
    statements.append("PRAGMA foreign_keys = ON;")
    return "\n\n".join(statements)


def runtime_profile(data: dict[str, Any], profile: str) -> dict[str, Any]:
    declared = profiles(data)[profile]
    runtime = declared.get("runtime", {})
    if not isinstance(runtime, dict):
        raise ValueError(f"Fixture profile has invalid runtime contract: {profile}")
    index = catalog_index(data)

    def resolve(key: str, group: str) -> dict[str, Any]:
        indexed_group, row = index.get(key, (None, None))
        if indexed_group != group or row is None:
            raise ValueError(f"Runtime profile references unknown {group} fixture: {key}")
        return row

    resolved = json.loads(json.dumps(runtime))
    resolved["demo_matrix_version"] = data["demo_matrix_version"]
    for role in resolved.get("roles", {}).values():
        account = resolve(role.pop("account_key"), "accounts")
        person = resolve(role.pop("person_key"), "persons")
        membership = resolve(role.pop("membership_key"), "memberships")
        role.update(
            {
                "account_id": account["id"],
                "person_id": person["id"],
                "committee_member_id": membership["id"],
                "display_name": f"{person['first_name']} {person['last_name']}",
                "account_email": account["email"],
                "person_email": person["email"],
            }
        )
    return resolved


def render_sql(
    data: dict[str, Any],
    profile: str = "development",
    *,
    reference_time: str | None = None,
) -> str:
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
        [row["id"], row["first_name"], row["last_name"], row["email"], row["mobile"]]
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
        [row["id"], 1, row["id"], row["attempt_number"], row["requires_mep"]] for row in candidates
    ]
    contact_room_sql = ""
    if contact_room_rows:
        contact_room_sql = (
            'INSERT INTO "exam_venue_contact_room" (contact_id, room_id) VALUES\n'
            + sql_rows(contact_room_rows)
            + ";"
        )
    core = f"""-- Generated by fixtures/generate.py. Do not edit directly.
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

INSERT INTO round_candidate
  (id, exam_round_id, candidate_id, attempt_number, requires_mep)
VALUES
{sql_rows(round_candidate_rows)};""".strip()
    records = render_seed_records(
        data,
        profile,
        excluded_ids=(
            {}
            if profile == "public-demo"
            else {"round_candidate": {row[0] for row in round_candidate_rows}}
        ),
        reference_time=reference_time,
    )
    return f"{core}\n\n{records}\n"


def render_profile_sql(
    data: dict[str, Any], profile: str, *, reference_time: str | None = None
) -> str:
    """Compile one complete SQL seed from the catalog and profile declaration."""
    if profile not in PROFILE_NAMES:
        raise ValueError(f"Unknown fixture profile: {profile}")
    return render_sql(data, profile, reference_time=reference_time)


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


def outputs(
    data: dict[str, Any],
    profile: str | None = None,
    *,
    output_dir: Path | None = None,
) -> dict[Path, str]:
    validate_catalog(data)
    if profile is not None and profile not in PROFILE_NAMES:
        raise ValueError(f"Unknown fixture profile: {profile}")
    sql_dir = output_dir or ROOT / "db"
    generated = {
        sql_dir / "seed_development.sql": render_sql(data, "development"),
        TYPESCRIPT_TARGET: render_typescript(data),
    }
    if profile is None or profile == "public-demo":
        generated[sql_dir / "seed_public_demo.sql"] = render_profile_sql(data, "public-demo")
    return generated


def generate(
    check: bool = False,
    profile: str | None = None,
    *,
    output_dir: Path | None = None,
) -> list[Path]:
    mismatches = []
    generated = outputs(load_source(), profile, output_dir=output_dir)
    for path, content in generated.items():
        if check:
            # SQL is deliberately a disposable build artifact.  --check still
            # compiles every profile, while only tracked generated adapters are
            # compared with the working tree.
            if path.name.startswith("seed_"):
                continue
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
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="directory for disposable generated SQL artifacts (default: db)",
    )
    args = parser.parse_args()
    mismatches = generate(check=args.check, profile=args.profile, output_dir=args.output_dir)
    if mismatches:
        for path in mismatches:
            print(f"outdated synthetic fixture adapter: {path.relative_to(ROOT)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
