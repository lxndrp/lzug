from __future__ import annotations

import json
import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.validate_demo_url_contract import (
    CANONICAL_DEMO_URL,
    DemoUrlContractError,
    validate_github_contract,
    validate_repository_demo_url,
)


class DemoUrlContractTests(unittest.TestCase):
    class Response:
        def __init__(self, payload: dict[str, str]) -> None:
            self.payload = payload

        def __enter__(self) -> DemoUrlContractTests.Response:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def test_only_the_confirmed_repository_demo_origin_is_accepted(self) -> None:
        self.assertEqual(CANONICAL_DEMO_URL, validate_repository_demo_url(CANONICAL_DEMO_URL))

        for invalid in (
            "https://demo.lzug.repertoire.papaspyrou.name/",
            "https://demo.example.invalid",
            "http://demo.lzug.repertoire.papaspyrou.name",
            "https://stage.papaspyrou.name",
            "https://lzug-demo-app.calmsea-4e736077.germanywestcentral.azurecontainerapps.io",
            "https://*.lzug.repertoire.papaspyrou.name",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(DemoUrlContractError):
                validate_repository_demo_url(invalid)

    def test_github_contract_requires_repository_value_and_no_environment_override(self) -> None:
        not_found = HTTPError(
            "https://api.github.com/repos/lxndrp/lzug/environments/demo/variables/DEMO_URL",
            404,
            "Not Found",
            Message(),
            BytesIO(),
        )
        with patch(
            "scripts.validate_demo_url_contract.urlopen",
            side_effect=[
                self.Response({"name": "DEMO_URL", "value": CANONICAL_DEMO_URL}),
                not_found,
            ],
        ):
            validate_github_contract(
                repository="lxndrp/lzug",
                token="test-token",
                effective_url=CANONICAL_DEMO_URL,
            )

        with (
            patch(
                "scripts.validate_demo_url_contract.urlopen",
                side_effect=[
                    self.Response({"name": "DEMO_URL", "value": CANONICAL_DEMO_URL}),
                    self.Response({"name": "DEMO_URL", "value": CANONICAL_DEMO_URL}),
                ],
            ),
            self.assertRaises(DemoUrlContractError),
        ):
            validate_github_contract(
                repository="lxndrp/lzug",
                token="test-token",
                effective_url=CANONICAL_DEMO_URL,
            )


if __name__ == "__main__":
    unittest.main()
