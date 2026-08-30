from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts import generate_synthetic_fixtures as generator


class SyntheticFixtureGeneratorTests(unittest.TestCase):
    def test_seed_requires_exactly_one_active_chair_per_committee(self) -> None:
        data = generator.load_source()
        generator.validate_seed_committees(data)

        missing = deepcopy(data)
        chair = next(member for member in missing["members"] if member["committee_role"] == "chair")
        chair["committee_role"] = "member"
        with self.assertRaisesRegex(ValueError, "exactly one active chair"):
            generator.outputs(missing)

        conflicting = deepcopy(data)
        deputy = next(
            member
            for member in conflicting["members"]
            if member["committee_role"] == "deputy_chair"
        )
        deputy["committee_role"] = "chair"
        with self.assertRaisesRegex(ValueError, "exactly one active chair"):
            generator.outputs(conflicting)

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
