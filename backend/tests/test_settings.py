from __future__ import annotations

import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from backend.settings import RuntimeSettings


class RuntimeSettingsTests(unittest.TestCase):
    def test_one_assembly_parses_all_runtime_domains(self) -> None:
        settings = RuntimeSettings.from_environment(
            {
                "LZUG_HOST": "0.0.0.0",
                "LZUG_PORT": "8080",
                "LZUG_DATABASE_PATH": "/srv/lzug.sqlite",
                "LZUG_MAX_UPLOAD_BYTES": "2048",
                "LZUG_HTTPS_ONLY": "false",
                "LZUG_CORS_ALLOWED_ORIGINS": "https://example.invalid,http://localhost:4200",
                "LZUG_MAP_PROVIDER": "osm",
                "LZUG_NOMINATIM_USER_AGENT": "lzug-test",
                "LZUG_SMTP_HOST": "smtp.example.invalid",
                "LZUG_SMTP_PORT": "2525",
                "LZUG_EXTERNAL_URL": "https://example.invalid",
                "LZUG_CALENDAR_TIMEZONE": "Europe/Berlin",
            }
        )

        self.assertEqual("0.0.0.0", settings.server.host)
        self.assertEqual(8080, settings.server.port)
        self.assertEqual(Path("/srv/lzug.sqlite"), Path(settings.persistence.database_path_value))
        self.assertEqual(2048, settings.documents.max_upload_bytes)
        self.assertFalse(settings.security.https_only)
        self.assertEqual(
            frozenset({"https://example.invalid", "http://localhost:4200"}),
            settings.security.cors_allowed_origins,
        )
        self.assertEqual("osm", settings.integrations.map_provider)
        self.assertEqual(2525, settings.notifications.smtp_port)

    def test_defaults_and_mutually_exclusive_database_sources_are_stable(self) -> None:
        settings = RuntimeSettings.from_environment({})

        self.assertEqual(Path("/data"), settings.persistence.data_dir)
        self.assertEqual(28800, settings.security.session_ttl_seconds)
        self.assertEqual(25, settings.notifications.smtp_port)
        with self.assertRaisesRegex(ValueError, "only one"):
            RuntimeSettings.from_environment(
                {"LZUG_DATABASE_PATH": "/data/a.sqlite", "LZUG_DATABASE_URL": "sqlite:///b"}
            )

    def test_secret_values_are_masked_in_representation_and_serialization(self) -> None:
        private_key = (
            ec.generate_private_key(ec.SECP256R1())
            .private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            .decode()
        )
        settings = RuntimeSettings.from_environment(
            {
                "LZUG_AUTH_ENCRYPTION_KEY": "auth-secret",
                "LZUG_SMTP_PASSWORD": "smtp-secret",
                "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": private_key,
                "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
            }
        )

        rendered = repr(settings) + str(settings.model_dump()) + settings.model_dump_json()
        self.assertNotIn("auth-secret", rendered)
        self.assertNotIn("smtp-secret", rendered)
        self.assertNotIn(private_key, rendered)
        self.assertEqual("smtp-secret", settings.notifications.smtp_password_value)

    def test_invalid_values_fail_before_runtime_assembly(self) -> None:
        for values, message in (
            ({"LZUG_MAX_UPLOAD_BYTES": "0"}, "LZUG_MAX_UPLOAD_BYTES"),
            ({"LZUG_ALLOWED_UPLOAD_MEDIA_TYPES": "image/*"}, "exact media types"),
            ({"LZUG_MAP_PROVIDER": "google"}, "NOMINATIM_USER_AGENT"),
            (
                {
                    "LZUG_WEB_PUSH_VAPID_PRIVATE_KEY": "push-secret",
                    "LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid",
                },
                "Invalid Web Push",
            ),
            ({"LZUG_WEB_PUSH_SUBJECT": "mailto:operator@example.invalid"}, "must be set together"),
        ):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, message):
                RuntimeSettings.from_environment(values)
