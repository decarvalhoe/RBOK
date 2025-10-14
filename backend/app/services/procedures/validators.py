"""Validation helpers for procedure slots and checklists."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, MutableMapping, Sequence

from .exceptions import ChecklistValidationError, SlotValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s().-]{3,}$")


class SlotValidator:
    """Validate slot payloads according to their declared type."""

    def __init__(self, definitions: Sequence[MutableMapping[str, Any]]) -> None:
        self._definitions = {definition.get("name"): dict(definition) for definition in definitions}

    def validate(self, values: MutableMapping[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        cleaned: Dict[str, Any] = {}

        for name, definition in self._definitions.items():
            raw_value = values.get(name)
            required = bool(definition.get("required", False))
            if raw_value in (None, ""):
                if required:
                    errors.append(f"Slot '{name}' is required")
                continue

            slot_type = definition.get("type", "string")
            try:
                cleaned[name] = self._coerce_value(name, slot_type, raw_value, definition)
            except SlotValidationError as exc:
                errors.append(str(exc))

        unknown_slots = set(values.keys()) - set(self._definitions.keys())
        if unknown_slots:
            errors.append(f"Unknown slots provided: {', '.join(sorted(unknown_slots))}")

        if errors:
            raise SlotValidationError("; ".join(errors))

        return cleaned

    def _coerce_value(
        self,
        name: str,
        slot_type: str,
        raw_value: Any,
        definition: MutableMapping[str, Any],
    ) -> Any:
        if slot_type == "string":
            if not isinstance(raw_value, str):
                raise SlotValidationError(f"Slot '{name}' must be a string")
            return raw_value.strip()

        if slot_type == "number":
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
                raise SlotValidationError(f"Slot '{name}' must be a number") from exc
            return value

        if slot_type == "enum":
            options = definition.get("options") or definition.get("choices")
            if not isinstance(options, Iterable):
                raise SlotValidationError(f"Slot '{name}' does not declare valid options")
            if raw_value not in options:
                raise SlotValidationError(
                    f"Slot '{name}' must be one of: {', '.join(map(str, options))}"
                )
            return raw_value

        if slot_type == "email":
            if not isinstance(raw_value, str) or not _EMAIL_RE.match(raw_value):
                raise SlotValidationError(f"Slot '{name}' must be a valid email address")
            return raw_value

        if slot_type == "phone":
            if not isinstance(raw_value, str) or not _PHONE_RE.match(raw_value):
                raise SlotValidationError(f"Slot '{name}' must be a valid phone number")
            return raw_value

        if slot_type == "date":
            if isinstance(raw_value, date):
                return raw_value.isoformat()
            if not isinstance(raw_value, str):
                raise SlotValidationError(f"Slot '{name}' must be an ISO formatted date")
            try:
                parsed = datetime.fromisoformat(raw_value)
            except ValueError as exc:
                raise SlotValidationError(f"Slot '{name}' must be an ISO formatted date") from exc
            return parsed.date().isoformat()

        raise SlotValidationError(f"Unsupported slot type '{slot_type}' for '{name}'")


class ChecklistValidator:
    """Validate checklist submissions according to their declaration."""

    def __init__(self, items: Sequence[MutableMapping[str, Any]]) -> None:
        self._items = {item.get("name"): dict(item) for item in items}

    def validate(self, submission: Sequence[MutableMapping[str, Any]] | MutableMapping[str, Any] | None) -> Dict[str, bool]:
        if not self._items:
            return {}

        if submission is None:
            submission_map: Dict[str, bool] = {}
        elif isinstance(submission, dict):
            submission_map = {str(key): bool(value) for key, value in submission.items()}
        else:
            submission_map = {
                str(item.get("name")): bool(item.get("completed", False))
                for item in submission
            }

        errors: List[str] = []
        cleaned: Dict[str, bool] = {}

        for name, definition in self._items.items():
            completed = bool(submission_map.get(name, False))
            cleaned[name] = completed
            if definition.get("required", False) and not completed:
                errors.append(f"Checklist item '{name}' must be completed")

        unknown_items = set(submission_map.keys()) - set(self._items.keys())
        if unknown_items:
            errors.append(f"Unknown checklist items provided: {', '.join(sorted(unknown_items))}")

        if errors:
            raise ChecklistValidationError("; ".join(errors))

        return cleaned
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
