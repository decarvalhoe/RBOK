"""Validation helpers for procedure slots and checklists."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple, TypedDict

from .exceptions import ChecklistValidationError, SlotValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s().-]{3,}$")

_SUPPORTED_TRUTHY = {"true", "1", "yes", "y", "on"}
_SUPPORTED_FALSY = {"false", "0", "no", "n", "off"}


class SlotDefinition(TypedDict, total=False):
    """Legacy slot definition structure used by :mod:`app.services.procedures.run`."""

    name: str
    type: str
    required: bool
    options: Iterable[Any]
    metadata: Mapping[str, Any]
    mask: str
    validate: str


class ValidationError(TypedDict):
    """Describe a validation error returned by :func:`validate_payload`."""

    field: str
    code: str
    params: Dict[str, Any]


SUPPORTED_SLOT_TYPES = {
    "string",
    "number",
    "integer",
    "boolean",
    "enum",
    "email",
    "phone",
    "date",
}


def _build_error(field: str, code: str, params: Optional[Dict[str, Any]] = None) -> ValidationError:
    return {"field": field, "code": code, "params": params or {}}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _compile_mask(mask: str) -> re.Pattern[str] | None:
    if "X" not in mask:
        return None
    parts: List[str] = []
    for char in mask:
        if char == "X":
            parts.append(r"\d")
        elif char == " ":
            parts.append(" ")
        else:
            parts.append(re.escape(char))
    pattern = "".join(parts)
    return re.compile(f"^{pattern}$")


class SlotValidator:
    """Validate slot payloads according to their declared type."""

    def __init__(self, definitions: Sequence[Mapping[str, Any]]) -> None:
        self._definitions: Dict[str, Dict[str, Any]] = {}
        for definition in definitions:
            name = str(definition.get("name") or "").strip()
            if not name:
                continue
            metadata = dict(definition.get("metadata") or {})
            slot_type = str(definition.get("type", "string") or "string").strip().lower()
            required = bool(definition.get("required", False))
            options = definition.get("options")
            if options is None:
                options = metadata.get("options") or metadata.get("choices")
            mask = definition.get("mask") or metadata.get("mask")
            pattern = definition.get("validate") or metadata.get("validate") or metadata.get("pattern")
            compiled_pattern = None
            if pattern:
                try:
                    compiled_pattern = re.compile(pattern)
                except re.error as exc:  # pragma: no cover - invalid configuration
                    raise ValueError(f"Invalid regex for slot '{name}': {pattern}") from exc
            compiled_mask = _compile_mask(mask) if mask else None
            normalised = {
                "name": name,
                "type": slot_type,
                "required": required,
                "metadata": metadata,
                "options": list(options) if options is not None else None,
                "mask": mask,
                "mask_regex": compiled_mask,
                "validate": pattern,
                "validate_regex": compiled_pattern,
            }
            self._definitions[name] = normalised

    def validate(self, values: MutableMapping[str, Any]) -> Dict[str, Any]:
        errors: List[ValidationError] = []
        messages: List[str] = []
        cleaned: Dict[str, Any] = {}

        provided_keys = set(values.keys())

        for name, definition in self._definitions.items():
            raw_value = values.get(name)
            if _is_blank(raw_value):
                if definition["required"]:
                    errors.append(_build_error(name, "validation.required"))
                    messages.append(f"Slot '{name}' is required")
                continue

            try:
                cleaned[name] = self._coerce_value(name, raw_value, definition)
            except SlotValidationError as exc:
                if exc.issues:
                    errors.extend(exc.issues)
                else:
                    errors.append(_build_error(name, "validation.invalid", {"message": str(exc)}))
                messages.append(str(exc))

        unknown_slots = sorted(provided_keys - set(self._definitions.keys()))
        if unknown_slots:
            message = f"Unknown slots provided: {', '.join(unknown_slots)}"
            messages.append(message)
            for slot in unknown_slots:
                errors.append(_build_error(slot, "validation.unexpected_slot"))

        if errors:
            raise SlotValidationError("; ".join(messages), issues=errors)

        return cleaned

    def _coerce_value(self, name: str, raw_value: Any, definition: Mapping[str, Any]) -> Any:
        slot_type = definition.get("type", "string")

        if slot_type not in SUPPORTED_SLOT_TYPES:
            raise SlotValidationError(
                f"Unsupported slot type '{slot_type}' for '{name}'",
                issues=[_build_error(name, "validation.unsupported", {"type": slot_type})],
            )

        if slot_type == "string":
            if not isinstance(raw_value, str):
                raise SlotValidationError(
                    f"Slot '{name}' must be a string",
                    issues=[_build_error(name, "validation.type", {"expected": "string"})],
                )
            value = raw_value.strip()
        elif slot_type == "number":
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise SlotValidationError(
                    f"Slot '{name}' must be a number",
                    issues=[_build_error(name, "validation.type", {"expected": "number"})],
                ) from exc
            if value.is_integer():
                value = int(value)
        elif slot_type == "integer":
            try:
                value = int(raw_value)
            except (TypeError, ValueError) as exc:
                raise SlotValidationError(
                    f"Slot '{name}' must be an integer",
                    issues=[_build_error(name, "validation.type", {"expected": "integer"})],
                ) from exc
        elif slot_type == "boolean":
            if isinstance(raw_value, bool):
                value = raw_value
            elif isinstance(raw_value, str):
                lowered = raw_value.strip().lower()
                if lowered in _SUPPORTED_TRUTHY:
                    value = True
                elif lowered in _SUPPORTED_FALSY:
                    value = False
                else:
                    raise SlotValidationError(
                        f"Slot '{name}' must be a boolean",
                        issues=[_build_error(name, "validation.type", {"expected": "boolean"})],
                    )
            elif isinstance(raw_value, (int, float)):
                value = bool(raw_value)
            else:
                raise SlotValidationError(
                    f"Slot '{name}' must be a boolean",
                    issues=[_build_error(name, "validation.type", {"expected": "boolean"})],
                )
        elif slot_type == "enum":
            options = definition.get("options")
            if not isinstance(options, list) or not options:
                raise SlotValidationError(
                    f"Slot '{name}' does not declare valid options",
                    issues=[_build_error(name, "validation.configuration", {"missing": "options"})],
                )
            if raw_value not in options:
                raise SlotValidationError(
                    f"Slot '{name}' must be one of: {', '.join(map(str, options))}",
                    issues=[_build_error(name, "validation.enum", {"allowed": options})],
                )
            value = raw_value
        elif slot_type == "email":
            if not isinstance(raw_value, str) or not _EMAIL_RE.match(raw_value):
                raise SlotValidationError(
                    f"Slot '{name}' must be a valid email address",
                    issues=[_build_error(name, "validation.email")],
                )
            value = raw_value
        elif slot_type == "phone":
            if not isinstance(raw_value, str) or not _PHONE_RE.match(raw_value):
                raise SlotValidationError(
                    f"Slot '{name}' must be a valid phone number",
                    issues=[_build_error(name, "validation.phone")],
                )
            value = raw_value
        elif slot_type == "date":
            if isinstance(raw_value, date) and not isinstance(raw_value, datetime):
                value = raw_value.isoformat()
            elif isinstance(raw_value, datetime):
                value = raw_value.date().isoformat()
            elif isinstance(raw_value, str):
                try:
                    parsed = datetime.fromisoformat(raw_value)
                except ValueError as exc:
                    raise SlotValidationError(
                        f"Slot '{name}' must be an ISO formatted date",
                        issues=[_build_error(name, "validation.date")],
                    ) from exc
                value = parsed.date().isoformat()
            else:
                raise SlotValidationError(
                    f"Slot '{name}' must be an ISO formatted date",
                    issues=[_build_error(name, "validation.date")],
                )
        else:  # pragma: no cover - defensive, already handled earlier
            value = raw_value

        mask_regex = definition.get("mask_regex")
        mask = definition.get("mask")
        if mask_regex is not None:
            as_text = str(value)
            if not mask_regex.fullmatch(as_text):
                raise SlotValidationError(
                    f"Slot '{name}' must follow mask {mask}",
                    issues=[_build_error(name, "validation.mask", {"mask": mask})],
                )

        pattern = definition.get("validate_regex")
        pattern_raw = definition.get("validate")
        if pattern is not None:
            as_text = str(value)
            if not pattern.fullmatch(as_text):
                raise SlotValidationError(
                    f"Slot '{name}' does not match expected pattern",
                    issues=[_build_error(name, "validation.pattern", {"pattern": pattern_raw})],
                )

        return value


class ChecklistValidator:
    """Validate checklist submissions according to their declaration."""

    def __init__(self, items: Sequence[Mapping[str, Any]]) -> None:
        self._items: Dict[str, Dict[str, Any]] = {}
        for item in items:
            name = str(item.get("name") or item.get("key") or "").strip()
            if not name:
                continue
            normalised = {
                "name": name,
                "required": bool(item.get("required", False)),
                "metadata": dict(item.get("metadata") or {}),
            }
            self._items[name] = normalised

    def validate(
        self, submission: Sequence[MutableMapping[str, Any]] | MutableMapping[str, Any] | None
    ) -> Dict[str, bool]:
        if not self._items:
            return {}

        submission_map: Dict[str, Any] = {}
        errors: List[ValidationError] = []
        messages: List[str] = []

        if submission is None:
            pass
        elif isinstance(submission, dict):
            for key, value in submission.items():
                str_key = str(key)
                if str_key in submission_map:
                    messages.append(f"Duplicate checklist item '{str_key}' provided")
                    errors.append(_build_error(f"checklist.{str_key}", "validation.duplicate"))
                    continue
                submission_map[str_key] = value
        else:
            for index, item in enumerate(submission):
                if not isinstance(item, Mapping):
                    field = f"checklist[{index}]"
                    messages.append("Checklist entries must be objects")
                    errors.append(_build_error(field, "validation.invalid_item"))
                    continue
                key = item.get("name") or item.get("key")
                if not key or not isinstance(key, str):
                    field = f"checklist[{index}]"
                    messages.append("Checklist entries require a 'name'")
                    errors.append(_build_error(field, "validation.missing_key"))
                    continue
                if key in submission_map:
                    messages.append(f"Duplicate checklist item '{key}' provided")
                    errors.append(_build_error(f"checklist.{key}", "validation.duplicate"))
                    continue
                submission_map[key] = item.get("completed")

        cleaned: Dict[str, bool] = {}

        for key, value in submission_map.items():
            if key not in self._items:
                errors.append(_build_error(f"checklist.{key}", "validation.unexpected_item"))
                messages.append(f"Unknown checklist item '{key}' provided")
                continue
            if not isinstance(value, bool):
                errors.append(_build_error(f"checklist.{key}", "validation.type", {"expected": "boolean"}))
                messages.append(f"Checklist item '{key}' must be a boolean")
                continue
            cleaned[key] = bool(value)

        for name, definition in self._items.items():
            completed = bool(cleaned.get(name, False))
            cleaned[name] = completed
            if definition.get("required", False) and not completed:
                errors.append(_build_error(f"checklist.{name}", "validation.required"))
                messages.append(f"Checklist item '{name}' must be completed")

        if errors:
            raise ChecklistValidationError("; ".join(messages), issues=errors)

        return cleaned


def validate_payload(
    definitions: Iterable[SlotDefinition], payload: Mapping[str, Any]
) -> Tuple[Dict[str, Any], List[ValidationError]]:
    """Validate a payload using legacy slot definitions."""

    normalised: List[Dict[str, Any]] = []
    for definition in definitions:
        metadata: Dict[str, Any] = {}
        source_metadata = definition.get("metadata") or {}
        metadata.update(dict(source_metadata))
        configuration = definition.get("configuration") if isinstance(definition, Mapping) else None
        if isinstance(configuration, Mapping):
            metadata.update(dict(configuration))
        normalised.append(
            {
                "name": definition.get("name"),
                "type": definition.get("type", "string"),
                "required": definition.get("required", False),
                "metadata": metadata,
                "options": definition.get("options"),
                "mask": definition.get("mask") or metadata.get("mask"),
                "validate": definition.get("validate") or metadata.get("validate") or metadata.get("pattern"),
            }
        )

    validator = SlotValidator(normalised)
    try:
        cleaned = validator.validate(dict(payload))
        return cleaned, []
    except SlotValidationError as exc:
        errors = exc.issues or [
            _build_error("slots", "validation.invalid", {"message": str(exc)})
        ]
        return {}, errors


__all__ = [
    "SlotValidator",
    "ChecklistValidator",
    "SlotDefinition",
    "ValidationError",
    "SUPPORTED_SLOT_TYPES",
    "validate_payload",
]
