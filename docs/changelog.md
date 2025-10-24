# Changelog

## 2025-10-24 – Procedural API alignment

### Added
- New `POST /runs/{run_id}/steps/{step_key}/commit` endpoint exposing a streamlined payload for real-time integrations.

### Changed
- `POST /runs/{run_id}/commit-step` now expects checklist submissions as structured objects (`key`, `completed`, optional `completed_at`) and surfaces enriched checklist status/progress aggregates.
- Run responses now include `checklist_statuses` (alias of `checklist_states`) and `checklist_progress` to simplify UX updates.

### Documentation
- Regenerated the OpenAPI specification in `docs/openapi.json`.
- Updated the procedural walkthrough (`docs/procedures.md`) to reflect the new request/response formats and validation error details for integrators.
