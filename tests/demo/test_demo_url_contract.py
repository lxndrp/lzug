from __future__ import annotations

import unittest

from scripts.validate_demo_url_contract import (
    CANONICAL_DEMO_URL,
    DemoUrlContractError,
    main,
    validate_effective_demo_url,
)


class DemoUrlContractTests(unittest.TestCase):
    def test_only_the_confirmed_repository_demo_origin_is_accepted(self) -> None:
        self.assertEqual(CANONICAL_DEMO_URL, validate_effective_demo_url(CANONICAL_DEMO_URL))

        for invalid in (
            "https://demo.lzug.repertoire.papaspyrou.name/",
            "https://demo.lzug.repertoire.papaspyrou.name/path",
            "https://demo.lzug.repertoire.papaspyrou.name?query=value",
            "https://demo.lzug.repertoire.papaspyrou.name#fragment",
            "https://demo.example.invalid",
            "http://demo.lzug.repertoire.papaspyrou.name",
            "https://stage.papaspyrou.name",
            "https://lzug-demo-app.calmsea-4e736077.germanywestcentral.azurecontainerapps.io",
            "https://*.lzug.repertoire.papaspyrou.name",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(DemoUrlContractError):
                validate_effective_demo_url(invalid)

    def test_cli_validates_the_actions_resolved_value_without_github_access(self) -> None:
        self.assertEqual(0, main(["validate", "--value", CANONICAL_DEMO_URL]))
        for invalid in ("", "https://demo.example.invalid"):
            with self.subTest(invalid=invalid):
                self.assertEqual(1, main(["validate", "--value", invalid]))


if __name__ == "__main__":
    unittest.main()
