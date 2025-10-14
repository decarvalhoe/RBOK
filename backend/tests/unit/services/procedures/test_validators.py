from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.procedures import validators


SCHEMA_PATH = Path(__file__).resolve().parents[5] / "docs" / "json_schema_procedure_v1.json"


def test_supported_types_cover_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    slot_type_enum = (
        schema["properties"]["steps"]["items"]["properties"]["slots"]["items"]["properties"]["type"]["enum"]
    )
    assert set(slot_type_enum).issubset(validators.SUPPORTED_SLOT_TYPES)


def test_required_slot_missing() -> None:
    slots = [
        {"name": "email", "type": "email", "required": True},
    ]
    cleaned, errors = validators.validate_payload(slots, {})
    assert cleaned == {}
    assert errors == [
        {"field": "email", "code": "validation.required", "params": {}},
    ]


def test_type_enforced() -> None:
    slots = [
        {"name": "full_name", "type": "string", "required": True},
    ]
    cleaned, errors = validators.validate_payload(slots, {"full_name": 123})
    assert cleaned == {}
    assert errors and errors[0]["code"] == "validation.type"


def test_email_validation() -> None:
    slots = [
        {"name": "email", "type": "email", "required": True},
    ]
    cleaned, errors = validators.validate_payload(slots, {"email": "not-an-email"})
    assert cleaned == {}
    assert errors == [
        {"field": "email", "code": "validation.email", "params": {}},
    ]


def test_enum_options_enforced() -> None:
    slots = [
        {
            "name": "language",
            "type": "enum",
            "required": True,
            "options": ["fr", "en"],
        }
    ]
    cleaned, errors = validators.validate_payload(slots, {"language": "es"})
    assert cleaned == {}
    assert errors == [
        {
            "field": "language",
            "code": "validation.enum",
            "params": {"allowed": ["fr", "en"]},
        }
    ]


def test_mask_validation() -> None:
    slots = [
        {
            "name": "phone",
            "type": "phone",
            "required": True,
            "mask": "+41 XX XXX XX XX",
        }
    ]
    cleaned, errors = validators.validate_payload(slots, {"phone": "+41 12 345 67 89"})
    assert cleaned == {"phone": "+41 12 345 67 89"}
    assert errors == []

    cleaned, errors = validators.validate_payload(slots, {"phone": "+41-12-345-6789"})
    assert cleaned == {}
    assert errors == [
        {
            "field": "phone",
            "code": "validation.mask",
            "params": {"mask": "+41 XX XXX XX XX"},
        }
    ]


def test_regex_constraint() -> None:
    slots = [
        {
            "name": "code",
            "type": "string",
            "required": True,
            "validate": r"^[A-Z]{2}$",
        }
    ]
    cleaned, errors = validators.validate_payload(slots, {"code": "AB"})
    assert cleaned == {"code": "AB"}
    assert errors == []

    cleaned, errors = validators.validate_payload(slots, {"code": "A1"})
    assert cleaned == {}
    assert errors == [
        {
            "field": "code",
            "code": "validation.pattern",
            "params": {"pattern": r"^[A-Z]{2}$"},
        }
    ]


def test_normalisation_of_values() -> None:
    slots = [
        {"name": "age", "type": "number", "required": True},
        {"name": "start", "type": "date", "required": True},
        {"name": "consent", "type": "boolean", "required": False},
    ]
    payload = {"age": "42", "start": "2024-05-10", "consent": "yes"}
    cleaned, errors = validators.validate_payload(slots, payload)
    assert errors == []
    assert cleaned == {"age": 42, "start": "2024-05-10", "consent": True}


def test_unexpected_slot_detected() -> None:
    slots = [
        {"name": "email", "type": "email", "required": False},
    ]
    cleaned, errors = validators.validate_payload(slots, {"unknown": "value"})
    assert cleaned == {}
    assert errors == [
        {"field": "unknown", "code": "validation.unexpected_slot", "params": {}},
    ]


def test_optional_blank_ignored() -> None:
    slots = [
        {"name": "note", "type": "string", "required": False},
    ]
    cleaned, errors = validators.validate_payload(slots, {"note": "   "})
    assert cleaned == {}
    assert errors == []


def test_invalid_regex_configuration_raises() -> None:
    slots = [
        {
            "name": "code",
            "type": "string",
            "required": True,
            "validate": "[unterminated",
        }
    ]
    with pytest.raises(ValueError):
        validators.validate_payload(slots, {"code": "AA"})
