from __future__ import annotations

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


def test_slot_validator_detects_unsupported_types() -> None:
    validator = validators.SlotValidator(
        [
            {"name": "consent", "type": "boolean", "required": False},
        ]
    )

    with pytest.raises(SlotValidationError) as exc:
        validator.validate({"consent": True})

    assert "Unsupported slot type" in str(exc.value)


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
            "params": {"message": "Slot 'email' must be a valid email address; Slot 'phone' must follow mask 'XXX'"},
        }
    ]


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

    assert "Unknown checklist items" in str(exc.value)


def test_checklist_validator_accepts_dictionary_submission() -> None:
    validator = validators.ChecklistValidator(
        [
            {"name": "consent", "required": True},
            {"name": "safety", "required": False},
        ]
    )

    cleaned = validator.validate({"consent": True})

    assert cleaned == {"consent": True, "safety": False}
