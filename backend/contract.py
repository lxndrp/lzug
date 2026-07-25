"""Validate JSON HTTP responses against the generated OpenAPI document.

The application deliberately generates its OpenAPI description from the same
resource metadata as the HTTP adapter.  These small, dependency-free checks
exercise the generated document against real handler responses in the backend
test suite.  They cover the JSON Schema vocabulary used by ``backend.openapi``
without introducing a second OpenAPI runtime into the product.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ContractValidationError(AssertionError):
    """A response does not match its documented OpenAPI contract."""


def validate_response(
    specification: Mapping[str, Any],
    method: str,
    path: str,
    status: int,
    payload: Any,
) -> None:
    """Validate a JSON response for one documented HTTP operation.

    Query parameters are intentionally ignored while matching paths.  The
    response schema itself remains authoritative for payload shape, mandatory
    fields, primitive types, enums, arrays, maps, and local ``$ref`` values.
    """
    operation_path = _operation_path(path)
    operation = specification.get("paths", {}).get(operation_path, {}).get(method.lower())
    if operation is None:
        raise ContractValidationError(f"Undocumented operation: {method.upper()} {path}")

    response = operation.get("responses", {}).get(str(status))
    if response is None:
        raise ContractValidationError(
            f"Undocumented status: {method.upper()} {operation_path} returned {status}"
        )

    content = response.get("content", {})
    if not content:
        if payload is not None:
            raise ContractValidationError(
                f"{method.upper()} {operation_path} {status} must not return a JSON payload"
            )
        return

    schema = content.get("application/json", {}).get("schema")
    if schema is None:
        raise ContractValidationError(
            f"{method.upper()} {operation_path} {status} has no JSON response schema"
        )
    _validate(schema, payload, specification, "response")


def _operation_path(path: str) -> str:
    path_without_query = path.partition("?")[0]
    parts = path_without_query.strip("/").split("/")
    normalized = []
    for part in parts:
        normalized.append("{id}" if part.isdecimal() else part)
    return "/" + "/".join(normalized)


def _validate(
    schema: Mapping[str, Any], value: Any, specification: Mapping[str, Any], location: str
) -> None:
    if "$ref" in schema:
        _validate(_resolve_ref(specification, schema["$ref"]), value, specification, location)
        return

    allowed_types = schema.get("type")
    if allowed_types is not None:
        types = allowed_types if isinstance(allowed_types, list) else [allowed_types]
        if not any(_is_type(value, expected) for expected in types):
            expected = " or ".join(types)
            raise ContractValidationError(
                f"{location}: expected {expected}, got {_value_type(value)}"
            )

    if "enum" in schema and value not in schema["enum"]:
        raise ContractValidationError(f"{location}: value {value!r} is not an allowed enum member")

    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for field in schema.get("required", []):
            if field not in value:
                raise ContractValidationError(f"{location}: missing required field {field!r}")
        for field, field_value in value.items():
            field_schema = properties.get(field)
            if field_schema is None and isinstance(schema.get("additionalProperties"), dict):
                field_schema = schema["additionalProperties"]
            if field_schema is not None:
                _validate(field_schema, field_value, specification, f"{location}.{field}")

    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate(schema["items"], item, specification, f"{location}[{index}]")


def _resolve_ref(specification: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise ContractValidationError(f"Unsupported OpenAPI reference: {reference}")
    resolved: Any = specification
    for part in reference.removeprefix("#/").split("/"):
        resolved = resolved[part]
    if not isinstance(resolved, Mapping):
        raise ContractValidationError(
            f"OpenAPI reference does not resolve to a schema: {reference}"
        )
    return resolved


def _is_type(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    raise ContractValidationError(f"Unsupported OpenAPI type: {expected}")


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    return type(value).__name__
