#!/usr/bin/env python3
"""Load the demo procedure via the public API."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests

DEFAULT_SOURCE = Path('docs/procedures/demo.json')


def _normalise_step(step: Dict[str, Any], position: int) -> Dict[str, Any]:
    return {
        'key': step['key'],
        'title': step['title'],
        'prompt': step['prompt'],
        'slots': step.get('slots', []),
        'checklists': step.get('checklists', []),
        'metadata': step.get('metadata', {}),
        'position': position,
    }


def _build_payload(raw: Dict[str, Any], actor: str) -> Dict[str, Any]:
    steps = [_normalise_step(step, index) for index, step in enumerate(raw.get('steps', []))]
    payload: Dict[str, Any] = {
        'actor': actor,
        'id': raw.get('id'),
        'name': raw['name'],
        'description': raw.get('description', ''),
        'metadata': raw.get('metadata', {}),
        'steps': steps,
    }
    return payload


def load_procedure(base_url: str, source: Path, actor: str) -> Dict[str, Any]:
    with source.open('r', encoding='utf-8') as handle:
        raw_payload = json.load(handle)

    payload = _build_payload(raw_payload, actor=actor)
    response = requests.post(f'{base_url.rstrip('/')}/procedures', json=payload, timeout=30)
    if response.status_code not in (200, 201):
        raise SystemExit(
            f'Failed to import procedure: {response.status_code} {response.text}'.strip()
        )
    return response.json()


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Import the demo incident-response procedure via the API.')
    parser.add_argument('--base-url', default='http://localhost:8000', help='Base URL of the backend API (default: %(default)s).')
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE, help='Path to the JSON payload to import.')
    parser.add_argument('--actor', default='demo-admin', help='Audit actor recorded for the import (default: %(default)s).')

    args = parser.parse_args(argv)

    try:
        result = load_procedure(args.base_url, args.source, args.actor)
    except FileNotFoundError as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f'Invalid JSON in {args.source}: {exc}', file=sys.stderr)
        return 1
    except requests.RequestException as exc:
        print(f'HTTP error while importing procedure: {exc}', file=sys.stderr)
        return 1
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1

    print('Procedure imported successfully:')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
