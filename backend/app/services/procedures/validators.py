from __future__ import annotations

"""Validation helpers for procedure step payloads."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, TypedDict

SUPPORTED_SLOT_TYPES = {
    "string",
    "number",
    "date",
    "enum",
    "phone",
    "email",
    "boolean",
}


class SlotDefinition(TypedDict, total=False):
    """Describe a slot as defined in the procedure schema."""

    name: str
    type: str
    required: bool
    validate: str
    mask: str
    options: List[str]


class ValidationError(TypedDict):
    """Structure describing a localisable validation error."""

    field: str
    code: str
    params: Dict[str, Any]


_EMAIL_PATTERN = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
_PHONE_PATTERN = re.compile(r"^\+?[0-9\s().-]{6,}$")


def _make_error(field: str, code: str, **params: Any) -> ValidationError:
    return ValidationError(field=field, code=code, params=params or {})


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True


def _validate_string(field: str, value: Any) -> Tuple[Optional[str], List[ValidationError]]:
    if not isinstance(value, str):
        return None, [_make_error(field, "validation.type", expected="string")]
    return value.strip(), []


def _validate_enum(slot: SlotDefinition, value: Any) -> Tuple[Optional[str], List[ValidationError]]:
    field = slot["name"]
    if not isinstance(value, str):
        return None, [_make_error(field, "validation.type", expected="enum")]
    options = slot.get("options")
    if not options:
        raise ValueError(f"Slot '{field}' of type enum must define options")
    candidate = value.strip()
    if candidate not in options:
        return None, [_make_error(field, "validation.enum", allowed=options)]
    return candidate, []


def _validate_number(field: str, value: Any) -> Tuple[Optional[Any], List[ValidationError]]:
    if isinstance(value, bool):
        return None, [_make_error(field, "validation.type", expected="number")]
    if isinstance(value, (int, float)):
        return value, []
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None, [_make_error(field, "validation.type", expected="number")]
        try:
            number = Decimal(candidate)
        except InvalidOperation:
            return None, [_make_error(field, "validation.type", expected="number")]
        if number == number.to_integral():
            return int(number), []
        return float(number), []
    return None, [_make_error(field, "validation.type", expected="number")]


def _validate_date(field: str, value: Any) -> Tuple[Optional[str], List[ValidationError]]:
    if not isinstance(value, str):
        return None, [_make_error(field, "validation.type", expected="date")]
    candidate = value.strip()
    try:
        parsed = date.fromisoformat(candidate)
    except ValueError:
        return None, [_make_error(field, "validation.date", expected="YYYY-MM-DD")]
    return parsed.isoformat(), []


def _validate_email(field: str, value: Any) -> Tuple[Optional[str], List[ValidationError]]:
    if not isinstance(value, str):
        return None, [_make_error(field, "validation.type", expected="email")]
    candidate = value.strip()
    if not _EMAIL_PATTERN.fullmatch(candidate):
        return None, [_make_error(field, "validation.email")]
    return candidate, []


def _validate_phone(field: str, value: Any) -> Tuple[Optional[str], List[ValidationError]]:
    if not isinstance(value, str):
        return None, [_make_error(field, "validation.type", expected="phone")]
    candidate = value.strip()
    if not _PHONE_PATTERN.fullmatch(candidate):
        return None, [_make_error(field, "validation.phone")]
    return candidate, []


def _validate_boolean(field: str, value: Any) -> Tuple[Optional[bool], List[ValidationError]]:
    if isinstance(value, bool):
        return value, []
    if isinstance(value, int) and value in (0, 1):
        return bool(value), []
    if isinstance(value, str):
        candidate = value.strip().lower()
        truthy = {"true", "1", "yes", "y"}
        falsy = {"false", "0", "no", "n"}
        if candidate in truthy:
            return True, []
        if candidate in falsy:
            return False, []
    return None, [_make_error(field, "validation.type", expected="boolean")]


_TYPE_VALIDATORS = {
    "string": lambda slot, value: _validate_string(slot["name"], value),
    "enum": _validate_enum,
    "number": lambda slot, value: _validate_number(slot["name"], value),
    "date": lambda slot, value: _validate_date(slot["name"], value),
    "email": lambda slot, value: _validate_email(slot["name"], value),
    "phone": lambda slot, value: _validate_phone(slot["name"], value),
    "boolean": lambda slot, value: _validate_boolean(slot["name"], value),
}


def _mask_to_regex(mask: str) -> re.Pattern[str]:
    parts: List[str] = []
    for char in mask:
        if char in {"X", "x"}:
            parts.append(r"\d")
        elif char == " ":
            parts.append(r"\s")
        else:
            parts.append(re.escape(char))
    pattern = "".join(parts)
    return re.compile(f"^{pattern}$")


def _apply_constraints(slot: SlotDefinition, value: Any) -> List[ValidationError]:
    errors: List[ValidationError] = []
    as_text = str(value) if value is not None else ""

    pattern = slot.get("validate")
    if pattern:
        try:
            regex = re.compile(pattern)
        except re.error as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid validation pattern for slot '{slot['name']}': {exc}") from exc
        if not regex.fullmatch(as_text):
            errors.append(_make_error(slot["name"], "validation.pattern", pattern=pattern))

    mask = slot.get("mask")
    if mask:
        try:
            mask_regex = _mask_to_regex(mask)
        except re.error as exc:  # pragma: no cover - defensive
            raise ValueError(f"Invalid mask for slot '{slot['name']}': {exc}") from exc
        if not mask_regex.fullmatch(as_text):
            errors.append(_make_error(slot["name"], "validation.mask", mask=mask))

    return errors


def validate_payload(
    slots: Iterable[SlotDefinition],
    payload: Mapping[str, Any],
) -> Tuple[Dict[str, Any], List[ValidationError]]:
    """Validate *payload* according to *slots* definitions.

    Returns a tuple of (cleaned_payload, errors). The payload is only
    populated with slots that passed validation.
    """

    slot_map: Dict[str, SlotDefinition] = {}
    for slot in slots:
        name = slot.get("name")
        if not name:
            continue
        slot_map[name] = slot

    errors: List[ValidationError] = []
    cleaned: Dict[str, Any] = {}

    for field in payload.keys():
        if field not in slot_map:
            errors.append(_make_error(field, "validation.unexpected_slot"))

    for name, slot in slot_map.items():
        provided = name in payload and _has_value(payload[name])
        if not provided:
            if slot.get("required"):
                errors.append(_make_error(name, "validation.required"))
            continue

        slot_type = slot.get("type", "string")
        if slot_type not in SUPPORTED_SLOT_TYPES:
            raise ValueError(f"Unsupported slot type '{slot_type}' for slot '{name}'")

        validator = _TYPE_VALIDATORS.get(slot_type)
        if validator is None:
            raise ValueError(f"No validator configured for slot type '{slot_type}'")

        value = payload[name]
        normalised, type_errors = validator(slot, value)
        errors.extend(type_errors)
        if type_errors:
            continue

        constraint_errors = _apply_constraints(slot, normalised)
        errors.extend(constraint_errors)
        if constraint_errors:
            continue

        cleaned[name] = normalised

    return cleaned, errors


__all__ = [
    "SlotDefinition",
    "ValidationError",
    "SUPPORTED_SLOT_TYPES",
    "validate_payload",
]
