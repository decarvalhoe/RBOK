# Proposed Follow-up Tasks

## Fix typo in checklist status model field
- **Location:** `backend/app/api/runs.py`, lines 75-142.
- **Issue:** The `ChecklistStatusModel` exposes a field named `completed_le`, which is a typographical error for `completed_at`. The serializer fills the value from `status.completed_at`, so the public schema leaks the misspelled key.
- **Proposed fix:** Rename the field to `completed_at` and update any serialization/tests expecting the typo so that the API response matches the underlying data attribute name.

## Fix bug in run checklist item serialization
- **Location:** `backend/app/api/runs.py`, lines 70-109.
- **Issue:** `RunChecklistItemState` only defines a `key` field, yet `_serialize_checklist_statuses` populates `label`, `completed`, and `completed_at`. Pydantic drops these extras, so API consumers never receive them.
- **Proposed fix:** Extend `RunChecklistItemState` to declare the additional fields (label/completed/completed_at) and ensure the response schema returns the values already produced by the serializer.

## Align documentation for checklist completion timestamps
- **Location:** `backend/app/api/runs.py`, lines 45-48.
- **Issue:** The `RunChecklistItemPayload.completed_at` field description states it "defaults to now when omitted", but `ProcedureRunService._build_checklist_states` leaves the timestamp as `None` unless the client sends one. Documentation should reflect actual behaviour or the service should implement the described default.
- **Proposed fix:** Update the docstring/description to explain that the timestamp remains null when omitted, or implement server-side defaulting so the behaviour matches the documentation.

## Improve run API integration test coverage
- **Location:** `backend/tests/test_runs_api.py`, lines 149-208.
- **Issue:** `test_run_lifecycle_success` only asserts the presence of checklist status keys, allowing the `completed_le` typo and missing serialized fields to slip through. It also relies solely on the legacy `/commit-step` endpoint.
- **Proposed fix:** Strengthen the test to validate the exact field names (`completed_at`) and values returned by both `/commit-step` and `/steps/{step_key}/commit` so schema regressions are caught immediately.
