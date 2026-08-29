from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_synthetic_fixtures as generator


class SyntheticFixtureGeneratorTests(unittest.TestCase):
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
