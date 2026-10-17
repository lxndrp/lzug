"""Validate HTTP responses against the generated OpenAPI JSON Schemas."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator, RefResolver


class ContractValidationError(AssertionError):
    """A response does not match its documented OpenAPI contract."""


def validate_response(
    specification: Mapping[str, Any],
    method: str,
    path: str,
    status: int,
    payload: Any,
) -> None:
    """Validate a response against the operation's complete JSON Schema.

    OpenAPI 3.1 schemas use JSON Schema 2020-12. The standard validator handles
    composition keywords, constants, references and additional properties,
    avoiding a partial in-house implementation.
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

    validator = Draft202012Validator(
        schema,
        resolver=RefResolver.from_schema(specification),
    )
    error = next(iter(validator.iter_errors(payload)), None)
    if error is not None:
        location = "response"
        suffix = "".join(
            f".{part}" if isinstance(part, str) else f"[{part}]" for part in error.absolute_path
        )
        raise ContractValidationError(f"{location}{suffix}: {error.message}")


def _operation_path(path: str) -> str:
    path_without_query = path.partition("?")[0]
    parts = path_without_query.strip("/").split("/")
    normalized = ["{id}" if part.isdecimal() else part for part in parts]
    return "/" + "/".join(normalized)
