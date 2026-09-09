"""Nested OpenAPI response validation retains precise failure locations."""

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

    def test_errors_retain_locations_and_type_required_enum_order(self) -> None:
        cases = (
            ([], "response: expected object, got list"),
            ({}, "response: missing required field 'items'"),
            ({"items": [{}]}, "response.items[0]: missing required field 'id'"),
            ({"items": [{"id": True}]}, "response.items[0].id: expected integer, got bool"),
            (
                {"items": [{"id": 1, "state": "other"}]},
                "response.items[0].state: value 'other' is not an allowed enum member",
            ),
            (
                {"items": [{"id": 1, "note": 3}]},
                "response.items[0].note: expected string or null, got int",
            ),
        )
        for value, message in cases:
            with self.subTest(message=message):
                with self.assertRaises(ContractValidationError) as error:
                    validate_response(self.document, "GET", "/example", 200, value)
                self.assertEqual(message, str(error.exception))
