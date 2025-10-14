"""Validation helpers for procedure slots and checklists."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple, TypedDict

from .exceptions import ChecklistValidationError, SlotValidationError

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+\d][\d\s().-]{3,}$")


class SlotDefinition(TypedDict, total=False):
    """Legacy slot definition structure used by :mod:`app.services.procedures.run`."""

    name: str
    type: str
    required: bool
    options: Iterable[Any]


class ValidationError(TypedDict):
    """Describe a validation error returned by :func:`validate_payload`."""

    field: str
    code: str
    params: Dict[str, Any]


class SlotValidator:
    """Validate slot payloads according to their declared type."""

    def __init__(self, definitions: Sequence[Mapping[str, Any]]) -> None:
        self._definitions: Dict[str, Dict[str, Any]] = {}
        for definition in definitions:
            name = str(definition["name"]).strip()
            metadata = dict(definition.get("metadata") or {})
            normalised = {
                "name": name,
                "type": str(definition.get("type", "string") or "string"),
                "required": bool(definition.get("required", False)),
                "metadata": metadata,
            }
            for key in ("options", "choices"):
                if key in definition and definition[key] is not None:
                    normalised[key] = definition[key]
                elif key in metadata and metadata[key] is not None:
                    normalised[key] = metadata[key]
            self._definitions[name] = normalised

    def validate(self, values: MutableMapping[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        cleaned: Dict[str, Any] = {}

        for name, definition in self._definitions.items():
            raw_value = values.get(name)
            required = bool(definition["required"])
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
        definition: Mapping[str, Any],
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

    def __init__(self, items: Sequence[Mapping[str, Any]]) -> None:
        self._items: Dict[str, Dict[str, Any]] = {}
        for item in items:
            name = str(item["name"]).strip()
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


def validate_payload(
    definitions: Iterable[SlotDefinition], payload: Mapping[str, Any]
) -> Tuple[Dict[str, Any], List[ValidationError]]:
    """Validate a payload using legacy slot definitions."""

    normalised = []
    for definition in definitions:
        metadata: Dict[str, Any] = {}
        options = definition.get("options")
        if options is not None:
            metadata["options"] = list(options)
        normalised.append(
            {
                "name": definition["name"],
                "type": definition.get("type", "string"),
                "required": definition.get("required", False),
                "metadata": metadata,
            }
        )

    validator = SlotValidator(normalised)
    try:
        cleaned = validator.validate(dict(payload))
        return cleaned, []
    except SlotValidationError as exc:
        error = ValidationError(field="slots", code="invalid", params={"message": str(exc)})
        return {}, [error]


__all__ = ["SlotValidator", "ChecklistValidator", "SlotDefinition", "ValidationError", "validate_payload"]
