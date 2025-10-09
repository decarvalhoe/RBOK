# Audit Log Compliance Guide

The Réalisons platform now persists every meaningful state change to the new `audit_events` table. This document captures the retention policy and the supported export workflow for compliance reviews.

## Retention policy

* **Default retention window** – Audit events are retained for **7 years**. This duration meets typical enterprise and regulatory expectations (GDPR Article 30, ISO 27001 A.12.4).
* **Immutable storage** – Rows are never updated in place; only inserts occur. Event payloads capture a diff of the before/after state for the associated entity. Any redactions must be performed by compliance leads through a supervised database migration.
* **Archival process** – Events older than 6 years are replicated weekly to cold storage (S3-Glacier class) while remaining available in the primary database until the 7-year mark. A quarterly job purges events past their retention deadline and records its own `audit_events` entry tagged with `action="audit.retention_prune"`.
* **Legal holds** – When legal or security holds are declared, the purge job must be paused via the `AUDIT_RETENTION_LOCK` feature flag. Documentation of the hold is stored in the governance tracker and referenced in the quarterly audit report.

## Exporting audit logs

1. **Authenticate as an auditor** – Obtain a bearer token with an account mapped to the `auditor` role.
   ```bash
   http POST :8000/auth/token username=audra password=auditpass
   ```
2. **Call the audit API** – Use the read-only `/audit-events` endpoint to filter the desired interval (e.g., all procedure changes from January 2025).
   ```bash
   http GET :8000/audit-events \
     "Authorization:Bearer <TOKEN>" \
     action==procedure.updated \
     since==2025-01-01T00:00:00Z \
     until==2025-01-31T23:59:59Z
   ```
3. **Persist to CSV** – Pipe the JSON output into the internal CLI helper to transform it to CSV for regulators:
   ```bash
   http GET :8000/audit-events "Authorization:Bearer <TOKEN>" > audit.json
   ./scripts/audit_export.py audit.json audit.csv
   ```
4. **Secure delivery** – Upload the CSV to the compliance SFTP endpoint (`sftp://compliance.realisons.local/audit/`) and record the transfer in the governance ticket.

> **Note:** Export payloads contain only diffs, so reviewers should reference the linked entity snapshots in the case file for full context.
