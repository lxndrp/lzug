from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fixtures import generate as generator


class SyntheticFixtureGeneratorTests(unittest.TestCase):
    def test_catalog_is_complete_safe_and_semantically_addressable(self) -> None:
        data = generator.load_source()

        generator.validate_catalog(data)
        index = generator.catalog_index(data)

        self.assertEqual(generator.FIXTURE_ROOT, data["fixture_root"])
        self.assertEqual(generator.REQUIRED_COVERAGE, set(data["coverage_matrix"]))
        self.assertEqual(
            generator.ACTIVE_ADAPTERS,
            {
                adapter
                for group in generator.ENTITY_GROUPS
                for row in data[group]
                for adapter in row.get("adapters", ())
            },
        )
        self.assertEqual({"development", "public-demo"}, set(data["profiles"]))
        self.assertIn("demo.487.absence", data["profiles"]["public-demo"]["scenarios"])
        self.assertIn("demo.487.planchange", data["profiles"]["public-demo"]["scenarios"])
        self.assertTrue(all(key.startswith(f"{generator.FIXTURE_ROOT}.") for key in index))
        self.assertEqual(
            {"chair", "examiner", "replacement"},
            {account["demo_role"] for account in data["accounts"] if account["demo_role"]},
        )
        self.assertTrue(
            all(
                person["email"].endswith("@demo.lzug.invalid") and person["mobile"] is None
                for person in data["persons"]
            )
        )
        self.assertTrue(
            all(
                organization["is_fictional"]
                and organization["contact"] is None
                and organization["country"] == "Griechenland"
                for organization in data["organizations"]
            )
        )

    def test_athens_catalog_matches_the_reviewed_demo_contract(self) -> None:
        data = generator.load_source()
        locations = {row["fixture_key"]: row for row in data["locations"]}
        rooms = {row["fixture_key"]: row for row in data["rooms"]}

        self.assertEqual(3, len(locations))
        self.assertEqual(6, len(rooms))
        self.assertEqual(2, len(data["location_contacts"]))
        self.assertEqual(
            {
                "name.papaspyrou.repertoire.lzug.fixture.location.global.zappeion",
                "name.papaspyrou.repertoire.lzug.fixture.location.committee.athen.gazi",
                "name.papaspyrou.repertoire.lzug.fixture.location.committee.feenwald.nationalgarden",
            },
            set(locations),
        )
        self.assertEqual(
            (37.971620, 23.736520, "global", True),
            self._location_contract(locations, "location.global.zappeion"),
        )
        self.assertEqual(
            (37.977779, 23.714099, "committee", True),
            self._location_contract(locations, "location.committee.athen.gazi"),
        )
        self.assertEqual(
            (37.973365, 23.737690, "committee", False),
            self._location_contract(locations, "location.committee.feenwald.nationalgarden"),
        )
        self.assertEqual(
            {
                "Theseussaal": 24,
                "Hippolytasaal": 12,
                "Werkstatt Handwerkerensemble": 18,
                "Prüfhalle Pyramus": 30,
                "Lichtung Oberon": 15,
                "Lichtung Titania": 15,
            },
            {room["name"]: room["capacity"] for room in rooms.values()},
        )
        self.assertTrue(
            all(location["source_retrieved_at"] == "2026-09-01" for location in locations.values())
        )
        self.assertTrue(all(contact["phone"] is None for contact in data["location_contacts"]))
        self.assertEqual(
            ["name.papaspyrou.repertoire.lzug.fixture.room.gazi.handwerkerensemble"],
            data["location_contacts"][1]["room_keys"],
        )

    @staticmethod
    def _location_contract(locations, suffix):
        location = locations[f"{generator.FIXTURE_ROOT}.{suffix}"]
        return (
            location["latitude"],
            location["longitude"],
            location["scope"],
            bool(location["is_accessible"]),
        )

    def test_seed_requires_exactly_one_active_chair_per_committee(self) -> None:
        data = generator.load_source()
        generator.validate_seed_committees(data)

        missing = deepcopy(data)
        chair = next(
            member
            for member in missing["memberships"]
            if member["fixture_key"].endswith("membership.chair.athen")
        )
        chair["committee_role"] = "member"
        with self.assertRaisesRegex(ValueError, "exactly one active chair"):
            generator.outputs(missing)

        conflicting = deepcopy(data)
        deputy = next(
            member
            for member in conflicting["memberships"]
            if member["fixture_key"].endswith("membership.deputy.athen")
        )
        deputy["committee_role"] = "chair"
        with self.assertRaisesRegex(ValueError, "exactly one active chair"):
            generator.outputs(conflicting)

    def test_catalog_rejects_duplicate_keys_forbidden_contacts_and_missing_coverage(self) -> None:
        data = generator.load_source()

        duplicate = deepcopy(data)
        duplicate["candidates"][0]["fixture_key"] = duplicate["persons"][0]["fixture_key"]
        with self.assertRaisesRegex(ValueError, "Duplicate semantic fixture key"):
            generator.outputs(duplicate)

        missing_key = deepcopy(data)
        del missing_key["rooms"][0]["fixture_key"]
        with self.assertRaisesRegex(ValueError, "Fixture key is missing"):
            generator.outputs(missing_key)

        short_key = deepcopy(data)
        short_key["rooms"][0]["fixture_key"] = "room.short"
        with self.assertRaisesRegex(ValueError, "invalid root"):
            generator.outputs(short_key)

        forbidden_email = deepcopy(data)
        forbidden_email["persons"][0]["email"] = "theseus@example.invalid"
        with self.assertRaisesRegex(ValueError, "forbidden domain"):
            generator.outputs(forbidden_email)

        phone = deepcopy(data)
        phone["persons"][0]["mobile"] = "+30 210 0000000"
        with self.assertRaisesRegex(ValueError, "phone numbers are forbidden"):
            generator.outputs(phone)

        incomplete = deepcopy(data)
        incomplete["coverage_matrix"].pop("demo_487_absence")
        with self.assertRaisesRegex(ValueError, "coverage matrix is incomplete"):
            generator.outputs(incomplete)

        obsolete_adapter = deepcopy(data)
        obsolete_adapter["candidates"][0]["adapters"].append("prototype")
        with self.assertRaisesRegex(ValueError, "unknown adapters: prototype"):
            generator.outputs(obsolete_adapter)

    def test_catalog_rejects_invalid_role_links_and_scenario_references(self) -> None:
        data = generator.load_source()

        invalid_role_link = deepcopy(data)
        invalid_role_link["accounts"][0]["membership_key"] = invalid_role_link["accounts"][1][
            "membership_key"
        ]
        with self.assertRaisesRegex(ValueError, "reference different people"):
            generator.outputs(invalid_role_link)

        unknown_scenario = deepcopy(data)
        unknown_scenario["persons"][0]["scenarios"].append("demo.unknown")
        with self.assertRaisesRegex(ValueError, "references unknown scenarios"):
            generator.outputs(unknown_scenario)

        uncovered = deepcopy(data)
        uncovered["persons"][0]["scenarios"] = []
        with self.assertRaisesRegex(ValueError, "has no scenario coverage"):
            generator.outputs(uncovered)

    def test_cross_committee_membership_and_legacy_ids_are_explicit(self) -> None:
        data = generator.load_source()
        cross_key = f"{generator.FIXTURE_ROOT}.person.crosscommittee"
        memberships = [row for row in data["memberships"] if row["person_key"] == cross_key]

        self.assertEqual(2, len(memberships))
        self.assertEqual(2, len({row["committee_key"] for row in memberships}))
        for mapping in data["legacy_mapping"]:
            _, target = generator.catalog_index(data)[mapping["fixture_key"]]
            self.assertEqual(mapping["technical_id"], target["id"])

    def test_repeated_generation_is_byte_identical(self) -> None:
        data = generator.load_source()
        first = generator.outputs(data)
        second = generator.outputs(deepcopy(data))

        self.assertEqual(first, second)

    def test_check_accepts_current_and_rejects_missing_or_outdated_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "synthetic-fixtures.generated.ts"
            expected = "generated fixture adapter\n"
            with patch.object(generator, "outputs", return_value={target: expected}):
                self.assertEqual([target], generator.generate(check=True))

                target.write_text("outdated fixture adapter\n", encoding="utf-8")
                self.assertEqual([target], generator.generate(check=True))

                target.write_text(expected, encoding="utf-8")
                self.assertEqual([], generator.generate(check=True))


if __name__ == "__main__":
    unittest.main()
