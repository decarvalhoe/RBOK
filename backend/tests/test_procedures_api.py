from __future__ import annotations

from typing import Any, Dict

from fastapi.testclient import TestClient


def _build_procedure_payload() -> Dict[str, Any]:
    return {
        'actor': 'demo-admin',
        'id': 'demo-procedure',
        'name': 'Demo procedure',
        'description': 'A complete lifecycle for testing',
        'steps': [
            {
                'key': 'introduction',
                'title': 'Introduction',
                'prompt': 'Say hello',
                'slots': [{'name': 'greeting', 'type': 'string'}],
            },
            {
                'key': 'summary',
                'title': 'Summary',
                'prompt': 'Wrap up the conversation',
                'slots': [],
            },
        ],
    }


def test_procedure_lifecycle_generates_audit_trail(client: TestClient) -> None:
    create_response = client.post('/procedures', json=_build_procedure_payload())
    assert create_response.status_code == 201
    created_procedure = create_response.json()
    assert created_procedure['id'] == 'demo-procedure'
    assert len(created_procedure['steps']) == 2

    list_response = client.get('/procedures')
    assert list_response.status_code == 200
    procedures = list_response.json()
    assert any(procedure['id'] == 'demo-procedure' for procedure in procedures)

    detail_response = client.get('/procedures/demo-procedure')
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload['steps'][0]['key'] == 'introduction'

    run_response = client.post('/runs', json={'actor': 'operator', 'procedure_id': 'demo-procedure'})
    assert run_response.status_code == 201
    run_payload = run_response.json()
    run_id = run_payload['id']
    assert run_payload['state'] == 'in_progress'

    first_commit = client.post(
        f'/runs/{run_id}/steps/introduction/commit',
        json={'actor': 'operator', 'payload': {'greeting': 'Bonjour'}},
    )
    assert first_commit.status_code == 200
    assert first_commit.json()['run']['state'] == 'in_progress'

    second_commit = client.post(
        f'/runs/{run_id}/steps/summary/commit',
        json={'actor': 'operator', 'payload': {'summary': 'All done'}},
    )
    assert second_commit.status_code == 200
    assert second_commit.json()['run']['state'] == 'completed'

    procedure_events = client.get(
        '/audit-events',
        params={'entity_type': 'procedure', 'entity_id': 'demo-procedure'},
    )
    assert procedure_events.status_code == 200
    actions = [event['action'] for event in procedure_events.json()]
    assert 'procedure.created' in actions

    run_events = client.get('/audit-events', params={'entity_type': 'procedure_run', 'entity_id': run_id})
    assert run_events.status_code == 200
    run_actions = [event['action'] for event in run_events.json()]
    assert 'run.created' in run_actions
    assert 'run.updated' in run_actions

    step_events = client.get(
        '/audit-events',
        params={'entity_type': 'procedure_run_step', 'entity_id': f'{run_id}:summary'},
    )
    assert step_events.status_code == 200
    step_actions = [event['action'] for event in step_events.json()]
    assert step_actions == ['run.step_committed']
