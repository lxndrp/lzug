from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from backend.fastapi_assembly import export_openapi_document


class FastApiAssemblyExportTests(unittest.TestCase):
    def test_publication_and_transport_profiles_keep_cookie_settings_distinct(self) -> None:
        captured = []

        def app_for(config):
            captured.append(config)
            return SimpleNamespace(openapi=lambda: {"paths": {"/api/health": {}}})

        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch("backend.fastapi_assembly.create_app", side_effect=app_for),
        ):
            export_openapi_document(Path(directory) / "transport.json", profile="transport")
            export_openapi_document(Path(directory) / "publication.json")

        transport, publication = captured
        self.assertEqual("lzug_session", transport.session_cookie_name)
        self.assertFalse(transport.cookie_secure)
        self.assertFalse(transport.https_only)
        self.assertEqual("__Host-lzug_session", publication.session_cookie_name)
        self.assertTrue(publication.cookie_secure)
        self.assertTrue(publication.https_only)

    def test_unsupported_profile_fails_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "openapi.json"
            with self.assertRaisesRegex(ValueError, "unsupported OpenAPI profile"):
                export_openapi_document(output, profile="unknown")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
