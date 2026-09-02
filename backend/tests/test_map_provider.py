from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from backend.database import session_scope
from backend.exam_venues import ExamVenueService, room_is_usable_for_committee
from backend.map_provider import (
    MapProviderConfig,
    MapProviderConfigurationError,
    MapProviderUnavailableError,
    NominatimGeocoder,
)
from backend.tests.helpers import ApiServer, TempDatabase, TestLzugHandler


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self) -> bytes:
        return self.body


class MapProviderTests(unittest.TestCase):
    def test_configuration_is_fail_closed_and_never_exposes_credentials(self) -> None:
        self.assertEqual("off", MapProviderConfig.from_environment({}).mode)
        with self.assertRaises(MapProviderConfigurationError):
            MapProviderConfig.from_environment({"LZUG_MAP_PROVIDER": "google"})
        with self.assertRaises(MapProviderConfigurationError):
            MapProviderConfig.from_environment({"LZUG_MAP_PROVIDER": "osm"})
        with self.assertRaises(MapProviderConfigurationError):
            MapProviderConfig.from_environment(
                {"LZUG_MAP_PROVIDER": "google", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"}
            )
        with self.assertRaises(MapProviderConfigurationError):
            MapProviderConfig.from_environment(
                {
                    "LZUG_MAP_PROVIDER": "osm",
                    "LZUG_NOMINATIM_URL": "http://nominatim.invalid/search",
                    "LZUG_NOMINATIM_USER_AGENT": "lzug-test",
                }
            )
        config = MapProviderConfig.from_environment(
            {
                "LZUG_MAP_PROVIDER": "google",
                "LZUG_NOMINATIM_USER_AGENT": "lzug-test@example.invalid",
                "LZUG_GOOGLE_MAPS_API_KEY": "secret-browser-key",
            }
        )
        self.assertEqual("google", config.public_contract()["mode"])
        self.assertNotIn("secret-browser-key", str(config.public_contract()))
        self.assertNotIn("nominatim_user_agent", config.public_contract())
        self.assertEqual(
            {"googleMapsEmbedKey": "secret-browser-key"}, config.browser_runtime_contract()
        )

    def test_google_browser_key_is_available_only_from_the_html_shell(self) -> None:
        class GoogleHandler(TestLzugHandler):
            map_provider = MapProviderConfig.from_environment(
                {
                    "LZUG_MAP_PROVIDER": "google",
                    "LZUG_NOMINATIM_USER_AGENT": "lzug-test",
                    "LZUG_GOOGLE_MAPS_API_KEY": "restricted-browser-key",
                }
            )

        with tempfile.TemporaryDirectory() as directory, TempDatabase() as db_path:
            static_dir = Path(directory)
            (static_dir / "index.html").write_text("<app-root></app-root>", encoding="utf-8")
            with (
                patch.object(GoogleHandler, "static_dir", static_dir),
                ApiServer(db_path, GoogleHandler) as api,
            ):
                status, headers, body = api.request_raw("GET", "/")
                venue_status, venues = api.request("GET", "/api/exam-venues")
            with (
                patch.object(TestLzugHandler, "static_dir", static_dir),
                ApiServer(db_path, TestLzugHandler) as api,
            ):
                off_status, _off_headers, off_body = api.request_raw("GET", "/")

        self.assertEqual(200, status)
        self.assertEqual("text/html", headers["content-type"])
        self.assertIn(b'data-google-maps-embed-key="restricted-browser-key"', body)
        self.assertEqual(200, venue_status)
        self.assertNotIn("restricted-browser-key", str(venues))
        self.assertEqual(200, off_status)
        self.assertEqual(b"<app-root></app-root>", off_body)

    def test_geocoder_sends_only_the_address_and_returns_a_small_candidate(self) -> None:
        config = MapProviderConfig.from_environment(
            {"LZUG_MAP_PROVIDER": "osm", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"}
        )
        with patch(
            "backend.map_provider.urlopen",
            return_value=_Response(b'[{"lat":"53.55","lon":"9.99","display_name":"hidden"}]'),
        ) as request:
            candidate = NominatimGeocoder(config).geocode("Testweg 1, 20095 Hamburg")

        self.assertEqual({"latitude": 53.55, "longitude": 9.99, "source": "nominatim"}, candidate)
        url = request.call_args.args[0].full_url
        self.assertIn("q=Testweg+1%2C+20095+Hamburg", url)
        self.assertNotIn("display_name", str(candidate))

    def test_geocoder_failure_has_no_retry_or_data_payload(self) -> None:
        config = MapProviderConfig.from_environment(
            {"LZUG_MAP_PROVIDER": "osm", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"}
        )
        with patch("backend.map_provider.urlopen", side_effect=TimeoutError) as request:
            with self.assertRaises(MapProviderUnavailableError):
                NominatimGeocoder(config).geocode("secret address")
        request.assert_called_once()

    def test_address_change_marks_existing_coordinates_for_review(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            venue = service.create_venue(
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Prüfungszentrum",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "Deutschland",
                    "accessibility_status": "confirmed",
                    "is_accessible": True,
                    "latitude": 53.55,
                    "longitude": 9.99,
                    "coordinate_status": "confirmed",
                    "coordinate_source": "nominatim",
                    "is_active": False,
                },
                actor_member_id=1,
            )
            updated = service.update_venue(
                venue["id"],
                {"expected_revision": venue["revision"], "street": "Testweg 2"},
                actor_member_id=1,
            )

        assert updated is not None
        self.assertEqual("needs_review", updated["coordinate_status"])
        self.assertEqual(53.55, updated["latitude"])
        self.assertEqual("nominatim", updated["coordinate_source"])

    def test_active_mode_blocks_unconfirmed_rooms_from_planning(self) -> None:
        with TempDatabase() as db_path:
            service = ExamVenueService(db_path)
            venue = service.create_venue(
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Prüfungszentrum",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "Deutschland",
                    "accessibility_status": "confirmed",
                    "is_accessible": True,
                    "coordinate_status": "missing",
                    "is_active": False,
                },
                actor_member_id=1,
            )
            room = service.create_room(
                venue["id"], {"name": "Saal", "is_active": True}, actor_member_id=1
            )
            service.update_venue(
                venue["id"],
                {"expected_revision": venue["revision"], "is_active": True},
                actor_member_id=1,
            )
            with session_scope(db_path) as session:
                with patch.dict(os.environ, {}, clear=True):
                    self.assertTrue(room_is_usable_for_committee(session, room["id"], 1))
                with patch.dict(
                    os.environ,
                    {"LZUG_MAP_PROVIDER": "osm", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"},
                    clear=True,
                ):
                    self.assertFalse(room_is_usable_for_committee(session, room["id"], 1))

    def test_explicit_geocoding_returns_a_candidate_without_mutating_the_venue(self) -> None:
        class OSMHandler(TestLzugHandler):
            map_provider = MapProviderConfig.from_environment(
                {"LZUG_MAP_PROVIDER": "osm", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"}
            )

        with TempDatabase() as db_path, ApiServer(db_path, OSMHandler) as api:
            status, venue = api.request(
                "POST",
                "/api/exam-venues",
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Prüfungszentrum",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "Deutschland",
                    "accessibility_status": "confirmed",
                    "is_accessible": True,
                    "coordinate_status": "missing",
                    "is_active": False,
                },
            )
            self.assertEqual(201, status)
            with patch(
                "backend.map_provider.urlopen",
                return_value=_Response(b'[{"lat":"53.55","lon":"9.99"}]'),
            ):
                status, candidate = api.request(
                    "POST",
                    f"/api/exam-venues/{venue['id']}/geocode",
                    {"expected_revision": venue["revision"]},
                )
            unchanged = ExamVenueService(db_path).get_venue(venue["id"])

        self.assertEqual(200, status)
        self.assertEqual({"latitude": 53.55, "longitude": 9.99, "source": "nominatim"}, candidate)
        assert unchanged is not None
        self.assertEqual("missing", unchanged["coordinate_status"])

    def test_provider_switch_keeps_confirmed_coordinates_without_a_provider_request(self) -> None:
        class OSMHandler(TestLzugHandler):
            map_provider = MapProviderConfig.from_environment(
                {"LZUG_MAP_PROVIDER": "osm", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"}
            )

        class GoogleHandler(TestLzugHandler):
            map_provider = MapProviderConfig.from_environment(
                {
                    "LZUG_MAP_PROVIDER": "google",
                    "LZUG_NOMINATIM_USER_AGENT": "lzug-test",
                    "LZUG_GOOGLE_MAPS_API_KEY": "restricted-browser-key",
                }
            )

        with TempDatabase() as db_path:
            venue = ExamVenueService(db_path).create_venue(
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Prüfungszentrum",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "Deutschland",
                    "accessibility_status": "confirmed",
                    "is_accessible": True,
                    "latitude": 53.55,
                    "longitude": 9.99,
                    "coordinate_status": "confirmed",
                    "coordinate_source": "nominatim",
                    "is_active": False,
                },
                actor_member_id=1,
            )
            seen = []
            for handler in (TestLzugHandler, OSMHandler, GoogleHandler, TestLzugHandler):
                with ApiServer(db_path, handler) as api:
                    status, item = api.request("GET", f"/api/exam-venues/{venue['id']}")
                self.assertEqual(200, status)
                seen.append(
                    (
                        item["map_provider"]["mode"],
                        item["latitude"],
                        item["longitude"],
                        item["coordinate_source"],
                    )
                )

        self.assertEqual(
            [
                ("off", 53.55, 9.99, "nominatim"),
                ("osm", 53.55, 9.99, "nominatim"),
                ("google", 53.55, 9.99, "nominatim"),
                ("off", 53.55, 9.99, "nominatim"),
            ],
            seen,
        )

    def test_quota_error_does_not_change_existing_coordinates(self) -> None:
        class OSMHandler(TestLzugHandler):
            map_provider = MapProviderConfig.from_environment(
                {"LZUG_MAP_PROVIDER": "osm", "LZUG_NOMINATIM_USER_AGENT": "lzug-test"}
            )

        with TempDatabase() as db_path, ApiServer(db_path, OSMHandler) as api:
            status, venue = api.request(
                "POST",
                "/api/exam-venues",
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Prüfungszentrum",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "Deutschland",
                    "accessibility_status": "confirmed",
                    "is_accessible": True,
                    "latitude": 53.55,
                    "longitude": 9.99,
                    "coordinate_status": "confirmed",
                    "coordinate_source": "nominatim",
                    "is_active": False,
                },
            )
            self.assertEqual(201, status)
            with patch(
                "backend.map_provider.urlopen",
                side_effect=HTTPError("https://nominatim.invalid", 429, "quota", {}, None),
            ) as request:
                status, error = api.request(
                    "POST",
                    f"/api/exam-venues/{venue['id']}/geocode",
                    {"expected_revision": venue["revision"]},
                )
            unchanged = ExamVenueService(db_path).get_venue(venue["id"])

        self.assertEqual(503, status)
        self.assertEqual("map_provider_unavailable", error["error"]["code"])
        request.assert_called_once()
        assert unchanged is not None
        self.assertEqual(53.55, unchanged["latitude"])
        self.assertEqual(9.99, unchanged["longitude"])
        self.assertEqual("confirmed", unchanged["coordinate_status"])
        self.assertEqual("nominatim", unchanged["coordinate_source"])

    def test_disabled_mode_neither_calls_nominatim_nor_changes_the_venue(self) -> None:
        with TempDatabase() as db_path, ApiServer(db_path) as api:
            status, venue = api.request(
                "POST",
                "/api/exam-venues",
                {
                    "scope": "committee",
                    "committee_id": 1,
                    "name": "Prüfungszentrum ohne Karte",
                    "street": "Testweg 1",
                    "postal_code": "20095",
                    "city": "Hamburg",
                    "country": "Deutschland",
                    "accessibility_status": "confirmed",
                    "is_accessible": True,
                    "coordinate_status": "missing",
                    "is_active": False,
                },
            )
            self.assertEqual(201, status)
            with patch("backend.map_provider.urlopen") as request:
                status, error = api.request(
                    "POST",
                    f"/api/exam-venues/{venue['id']}/geocode",
                    {"expected_revision": venue["revision"]},
                )
            unchanged = ExamVenueService(db_path).get_venue(venue["id"])

        self.assertEqual(409, status)
        self.assertEqual("map_provider_disabled", error["error"]["code"])
        request.assert_not_called()
        assert unchanged is not None
        self.assertEqual("missing", unchanged["coordinate_status"])


if __name__ == "__main__":
    unittest.main()
