from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


class MessageConstraintConfig(TypedDict):
    minLength: int
    maxLength: int


_SHARED_CONSTRAINTS_PATH = (
    Path(__file__).resolve().parents[2] / 'shared' / 'message-constraints.json'
)

with _SHARED_CONSTRAINTS_PATH.open('r', encoding='utf-8') as fp:
    _constraints = json.load(fp)

MESSAGE_CONSTRAINTS: MessageConstraintConfig = _constraints['message']
MESSAGE_MIN_LENGTH: int = MESSAGE_CONSTRAINTS['minLength']
MESSAGE_MAX_LENGTH: int = MESSAGE_CONSTRAINTS['maxLength']

__all__ = ['MESSAGE_CONSTRAINTS', 'MESSAGE_MIN_LENGTH', 'MESSAGE_MAX_LENGTH']
