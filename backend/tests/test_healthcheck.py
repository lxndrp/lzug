from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from backend.healthcheck import public_health_ready


class HealthResponse(io.BytesIO):
    def __init__(self, payload: object, status: int) -> None:
        super().__init__(json.dumps(payload).encode())
        self.status = status

    def __enter__(self) -> HealthResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


class HealthcheckTests(unittest.TestCase):
    def response(self, payload: object, status: int = 200) -> HealthResponse:
        return HealthResponse(payload, status)

    def test_accepts_only_a_successful_ok_payload(self) -> None:
        with patch("backend.healthcheck.urlopen", return_value=self.response({"status": "ok"})):
            self.assertTrue(public_health_ready("http://127.0.0.1:8000/api/health"))

        for payload, status in (({"status": "ready"}, 200), ({"status": "ok"}, 503)):
            with self.subTest(payload=payload, status=status):
                with patch(
                    "backend.healthcheck.urlopen",
                    return_value=self.response(payload, status),
                ):
                    self.assertFalse(public_health_ready("http://127.0.0.1:8000/api/health"))

    def test_returns_false_for_invalid_configuration_response_and_transport(self) -> None:
        with patch(
            "backend.healthcheck.RuntimeSettings.from_environment",
            side_effect=ValueError("invalid"),
        ) as settings:
            self.assertFalse(public_health_ready())
            settings.assert_called_once_with()

        for failure in (OSError("offline"), URLError("offline"), ValueError("invalid json")):
            with self.subTest(failure=type(failure).__name__):
                with patch("backend.healthcheck.urlopen", side_effect=failure):
                    self.assertFalse(public_health_ready("http://127.0.0.1:8000/api/health"))


if __name__ == "__main__":
    unittest.main()
