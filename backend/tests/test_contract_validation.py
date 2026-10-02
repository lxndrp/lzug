"""OpenAPI contract tests use complete JSON Schema validation semantics."""

from __future__ import annotations

import unittest

from backend.application.contract import ContractValidationError, validate_response


class ContractValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = {
            "paths": {
                "/example": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Result"}
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "components": {
                "schemas": {
                    "Result": {
                        "type": "object",
                        "required": ["items"],
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["id"],
                                    "properties": {
                                        "id": {"type": "integer"},
                                        "state": {"enum": ["open", "closed"]},
                                    },
                                    "additionalProperties": {"type": ["string", "null"]},
                                },
                            }
                        },
                    }
                }
            },
        }

    def test_nested_maps_arrays_nullable_values_and_local_references(self) -> None:
        validate_response(
            self.document,
            "GET",
            "/example",
            200,
            {"items": [{"id": 1, "state": "open", "note": None}, {"id": 2, "note": "Text"}]},
        )

    def test_errors_retain_locations(self) -> None:
        cases = (
            ([], "response"),
            ({}, "response"),
            ({"items": [{}]}, "response.items[0]"),
            ({"items": [{"id": True}]}, "response.items[0].id"),
            (
                {"items": [{"id": 1, "state": "other"}]},
                "response.items[0].state",
            ),
            (
                {"items": [{"id": 1, "note": 3}]},
                "response.items[0].note",
            ),
        )
        for value, location in cases:
            with self.subTest(location=location):
                with self.assertRaises(ContractValidationError) as error:
                    validate_response(self.document, "GET", "/example", 200, value)
                self.assertTrue(str(error.exception).startswith(location))

    def test_json_schema_composition_constants_and_closed_objects_are_enforced(self) -> None:
        self.document["components"]["schemas"]["Result"] = {
            "type": "object",
            "required": ["session", "status"],
            "properties": {
                "session": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "status": {"const": "draft"},
            },
            "additionalProperties": False,
        }

        for value in (
            {"session": "17", "status": "draft"},
            {"session": None, "status": "active"},
            {"session": 17, "status": "draft", "extra": True},
        ):
            with self.subTest(value=value), self.assertRaises(ContractValidationError):
                validate_response(self.document, "GET", "/example", 200, value)

        validate_response(
            self.document,
            "GET",
            "/example",
            200,
            {"session": None, "status": "draft"},
        )
