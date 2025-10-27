from __future__ import annotations

from datetime import datetime

import pytest

from app.services.procedures import validators
from app.services.procedures.exceptions import ChecklistValidationError, SlotValidationError


def test_slot_validator_accepts_valid_payload() -> None:
    validator = validators.SlotValidator(
        [
            {
                "name": "email",
                "type": "email",
                "required": True,
            },
            {
                "name": "phone",
                "type": "phone",
                "required": False,
                "metadata": {"mask": "+41 XX XXX XX XX"},
            },
        ]
    )

    cleaned = validator.validate({"email": "user@example.com", "phone": "+41 21 555 77 88"})

    assert cleaned["email"] == "user@example.com"
    assert cleaned["phone"] == "+41 21 555 77 88"


def test_slot_validator_reports_multiple_issues() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "code", "type": "string", "required": True},
            {"name": "phone", "type": "phone", "required": True, "metadata": {"mask": "XXX"}},
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"phone": "1234", "unknown": "value"})

    message = str(exc.value)
    assert "Slot 'code' is required" in message
    assert "must follow mask" in message
    assert "Unknown slots provided" in message


def test_slot_validator_trims_optional_strings() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "notes", "type": "string", "required": False},
        ]
    )

    cleaned = validator.validate({"notes": "  Hello  "})

    assert cleaned["notes"] == "Hello"


def test_slot_validator_rejects_unsupported_slot_type() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "consent", "type": "boolean", "required": False},
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"consent": True})

    assert "Unsupported slot type" in str(exc.value)
    assert exc.value.issues == [
        {
            "field": "consent",
            "code": "validation.unsupported",
            "params": {"type": "boolean"},
        }
    ]


def test_validate_payload_wraps_slot_errors() -> None:
    cleaned, errors = validators.validate_payload(
        [
            {"name": "email", "type": "email", "required": True},
            {"name": "phone", "type": "phone", "mask": "XXX", "required": False},
        ],
        {"email": "invalid", "phone": "1234"},
    )

    assert cleaned == {}
    assert errors == [
        {
            "field": "slots",
            "code": "invalid",
            "params": {
                "message": "Slot 'email' must be a valid email address; Slot 'phone' must follow mask 'XXX'",
            },
        }
    ]


def test_slot_validator_supports_numeric_and_pattern_constraints() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "count", "type": "number", "required": True},
            {"name": "code", "type": "integer", "required": True},
            {"name": "role", "type": "enum", "options": ["admin", "user"]},
            {
                "name": "badge",
                "type": "string",
                "mask": "ID-XXX",
                "validate": r"^ID-\d{3}$",
            },
        ]
    )

    cleaned = validator.validate(
        {"count": "3.0", "code": "42", "role": "user", "badge": "ID-123"}
    )

    assert cleaned == {"count": 3, "code": 42, "role": "user", "badge": "ID-123"}


def test_slot_validator_reports_numeric_and_pattern_errors() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "count", "type": "number"},
            {"name": "code", "type": "integer"},
            {"name": "role", "type": "enum", "options": ["admin", "user"]},
            {
                "name": "badge",
                "type": "string",
                "mask": "ID-XXX",
                "validate": r"^ID-1\d{2}$",
            },
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"count": "foo", "code": "abc", "role": "guest", "badge": "ID-223"})

    issues = {(issue["field"], issue["code"]) for issue in exc.value.issues}
    assert issues == {
        ("count", "validation.type"),
        ("code", "validation.type"),
        ("role", "validation.enum"),
        ("badge", "validation.pattern"),
    }


def test_slot_validator_handles_date_inputs_and_masks() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "start", "type": "date"},
            {"name": "end", "type": "date"},
            {"name": "code", "type": "string", "mask": "XX XX"},
        ]
    )

    cleaned = validator.validate(
        {
            "start": datetime(2024, 5, 4),
            "end": "2024-05-05T01:02:03",
            "code": "12 34",
        }
    )

    assert cleaned == {
        "start": "2024-05-04",
        "end": "2024-05-05",
        "code": "12 34",
    }


def test_slot_validator_treats_blank_optional_strings_as_missing() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "notes", "type": "string", "required": False},
            {"name": "email", "type": "email", "required": True},
        ]
    )

    with pytest.raises(SlotValidationError):
        validator.validate({"notes": "   ", "email": "invalid"})


def test_slot_validator_rejects_missing_enum_configuration() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "role", "type": "enum"},
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"role": "admin"})

    assert exc.value.issues[0]["code"] == "validation.configuration"


def test_slot_validator_rejects_invalid_phone_numbers() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "phone", "type": "phone"},
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"phone": "not-a-number"})

    assert exc.value.issues == [
        {"field": "phone", "code": "validation.phone", "params": {}},
    ]


def test_slot_validator_rejects_invalid_dates() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "start", "type": "date"},
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"start": "not-a-date"})

    assert exc.value.issues[0]["code"] == "validation.date"


def test_validate_payload_merges_configuration_metadata() -> None:
    cleaned, errors = validators.validate_payload(
        [
            {
                "name": "code",
                "type": "string",
                "configuration": {"mask": "XX", "pattern": r"^[A-Z]{2}$"},
            }
        ],
        {"code": "A1"},
    )

    assert cleaned == {}
    assert errors[0]["code"] == "invalid"


def test_compile_mask_ignores_missing_placeholders() -> None:
    assert validators._compile_mask("ABC") is None


def test_build_mask_regex_supports_literals_and_digits() -> None:
    pattern = validators._build_mask_regex("ID-XX")

    assert pattern.fullmatch("ID-42")
    assert not pattern.fullmatch("ID-4A")


def test_checklist_validator_enforces_required_items() -> None:
    validator = validators.ChecklistValidator(
        [
            {"name": "consent", "required": True},
            {"name": "safety", "required": False},
        ]
    )

    with pytest.raises(ChecklistValidationError) as exc:
        validator.validate([
            {"name": "consent", "completed": False},
            {"name": "safety", "completed": True},
        ])

    assert "consent" in str(exc.value)


def test_checklist_validator_detects_unknown_items() -> None:
    validator = validators.ChecklistValidator(
        [
            {"name": "consent", "required": True},
        ]
    )

    with pytest.raises(ChecklistValidationError) as exc:
        validator.validate({"unknown": True})

    assert "Unknown checklist item" in str(exc.value)
    assert {(issue["field"], issue["code"]) for issue in exc.value.issues} == {
        ("checklist.unknown", "validation.unexpected_item"),
        ("checklist.consent", "validation.required"),
    }


def test_checklist_validator_accepts_dictionary_submission() -> None:
    validator = validators.ChecklistValidator(
        [
            {"name": "consent", "required": True},
            {"name": "safety", "required": False},
        ]
    )

    cleaned = validator.validate({"consent": True})

    assert cleaned == {"consent": True, "safety": False}
