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
