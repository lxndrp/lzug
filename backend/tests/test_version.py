from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import version


class VersionTests(unittest.TestCase):
    def tearDown(self) -> None:
        version._source_version.cache_clear()

    def test_source_version_is_read_once(self) -> None:
        version._source_version.cache_clear()

        with (
            patch.dict(os.environ, {"LZUG_VERSION": ""}),
            patch.object(Path, "read_text", return_value="1.2.3\n") as read_text,
        ):
            self.assertEqual("1.2.3", version.application_version())
            self.assertEqual("1.2.3", version.application_version())

        read_text.assert_called_once_with(encoding="utf-8")

    def test_environment_override_remains_dynamic(self) -> None:
        with patch.dict(os.environ, {"LZUG_VERSION": "1.2.3"}):
            self.assertEqual("1.2.3", version.application_version())

        with patch.dict(os.environ, {"LZUG_VERSION": "2.0.0"}):
            self.assertEqual("2.0.0", version.application_version())


if __name__ == "__main__":
    unittest.main()
