"""Tests covering the serialization helpers."""
from __future__ import annotations

from datetime import datetime

from app import models
from app.utils.serialization import serialize_procedure, serialize_run


def _build_procedure() -> models.Procedure:
    procedure = models.Procedure(
        id="proc-1",
        name="Test procedure",
        description="Ensure serialization", 
        metadata_payload={"version": "1.0"},
    )
    step = models.ProcedureStep(
        id="step-1",
        procedure=procedure,
        key="introduction",
        title="Introduction",
        prompt="Say hello",
        position=0,
        metadata_payload={"category": "demo"},
    )
    slot = models.ProcedureSlot(
        id="slot-1",
        step=step,
        name="greeting",
        label="Greeting",
        slot_type="string",
        required=True,
        position=0,
        configuration={
            "mask": "+41 XX XXX XX XX",
            "options": ["hello", "bonjour"],
            "validate": r"^[A-Za-z]+$",
        },
    )
    checklist_item = models.ProcedureStepChecklistItem(
        id="item-1",
        step=step,
        key="safety_ack",
        label="Safety acknowledgement",
        description="Operator confirmed safety instructions",
        required=True,
        position=0,
    )

    # Wire relationships explicitly for clarity.
    procedure.steps = [step]
    step.slots = [slot]
    step.checklist_items = [checklist_item]

    return procedure


def test_serialize_procedure_returns_plain_dict_structure() -> None:
    procedure = _build_procedure()

    payload = serialize_procedure(procedure)

    assert payload == {
        "id": "proc-1",
        "name": "Test procedure",
        "description": "Ensure serialization",
        "metadata": {"version": "1.0"},
        "steps": [
            {
                "id": "step-1",
                "key": "introduction",
                "title": "Introduction",
                "prompt": "Say hello",
                "position": 0,
                "metadata": {"category": "demo"},
                "slots": [
                    {
                        "name": "greeting",
                        "type": "string",
                        "required": True,
                        "label": "Greeting",
                        "description": None,
                        "validate": r"^[A-Za-z]+$",
                        "mask": "+41 XX XXX XX XX",
                        "options": ["hello", "bonjour"],
                        "position": 0,
                        "metadata": {
                            "mask": "+41 XX XXX XX XX",
                            "options": ["hello", "bonjour"],
                            "validate": r"^[A-Za-z]+$",
                        },
                        "id": "slot-1",
                    }
                ],
                "checklists": [
                    {
                        "key": "safety_ack",
                        "label": "Safety acknowledgement",
                        "description": "Operator confirmed safety instructions",
                        "required": True,
                        "default_state": None,
                        "position": 0,
                        "metadata": {},
                        "id": "item-1",
                    }
                ],
            }
        ],
    }

    assert isinstance(payload["steps"], list)
    assert isinstance(payload["steps"][0]["slots"], list)
    assert isinstance(payload["steps"][0]["slots"][0], dict)


def test_serialize_run_embeds_serialized_procedure() -> None:
    procedure = _build_procedure()
    run = models.ProcedureRun(
        id="run-1",
        procedure=procedure,
        procedure_id=procedure.id,
        user_id="user-1",
        state="in_progress",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        closed_at=None,
    )
    step_state = models.ProcedureRunStepState(
        id="state-1",
        run=run,
        run_id=run.id,
        step_key="introduction",
        payload={"greeting": "hello"},
        committed_at=datetime(2024, 1, 1, 12, 30, 0),
    )

    payload = serialize_run(run, [step_state])

    assert payload["id"] == "run-1"
    assert payload["procedure_id"] == procedure.id
    assert payload["created_at"] == "2024-01-01T12:00:00"
    assert payload["closed_at"] is None

    assert payload["procedure"] == serialize_procedure(procedure)

    assert payload["step_states"] == [
        {
            "id": "state-1",
            "step_key": "introduction",
            "payload": {"greeting": "hello"},
            "committed_at": "2024-01-01T12:30:00",
        }
    ]

    # Ensure we returned a copy of the payload to avoid accidental mutation leaks.
    assert payload["step_states"][0]["payload"] is not step_state.payload
