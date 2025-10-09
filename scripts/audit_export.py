#!/usr/bin/env python3
"""Utility to transform audit event JSON into CSV for regulators."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable


FIELDNAMES = [
    "id",
    "occurred_at",
    "actor",
    "action",
    "entity_type",
    "entity_id",
    "payload_diff",
]


def load_events(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
        if not isinstance(data, list):
            raise ValueError("Audit export expects a list of events")
        return data


def dump_csv(events: Iterable[Dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDNAMES)
        writer.writeheader()
        for event in events:
            row = {key: event.get(key, "") for key in FIELDNAMES}
            if isinstance(row["payload_diff"], (dict, list)):
                row["payload_diff"] = json.dumps(row["payload_diff"], ensure_ascii=False)
            writer.writerow(row)


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("Usage: audit_export.py <input.json> <output.csv>", file=sys.stderr)
        return 1

    input_path = Path(argv[1])
    output_path = Path(argv[2])
    events = load_events(input_path)
    dump_csv(events, output_path)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    raise SystemExit(main(sys.argv))
