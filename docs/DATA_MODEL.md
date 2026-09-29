# Data model

## Canonical work fields

`work_id, description, state, district, constituency, category, agency, sanction_amount,
expenditure, progress_percent, sanction_date, expected_completion, actual_completion, status,
latitude, longitude`

Every upload records, per field, whether it is AVAILABLE, UNAVAILABLE, DERIVED or INFERRED in
`field_mappings`. Fields with no source column are surfaced as **"Not present in current
dataset"** rather than invented.

Mandatory for oversight: `work_id, description, state, district, category, agency,
sanction_amount, expenditure, sanction_date`.

## Tables

| Group | Tables |
| --- | --- |
| Identity | `users` |
| Ingestion | `datasets`, `field_mappings` |
| Domain | `works` |
| Risk | `risk_scores`, `risk_signals`, `risk_rules`, `risk_rule_versions`, `peer_groups`, `model_versions` |
| Quality | `data_quality_results` (RECORD and DATASET scope) |
| Verification | `verification_cases`, `case_status_history`, `case_assignments`, `case_notes`, `evidence` |
| Platform | `notifications`, `audit_logs`, `system_config` |

`risk_scores.work_id` is the foreign key to `works.id`; `works.work_id` is the business
reference printed in the UI. Risk factors are stored as JSON on `risk_scores` alongside the
rule versions used.

## Case status machine

```
OPEN -> ASSIGNED | UNDER_REVIEW | ESCALATED | CLOSED
ASSIGNED -> UNDER_REVIEW | FIELD_VERIFICATION | ESCALATED | OPEN | CLOSED
UNDER_REVIEW -> FIELD_VERIFICATION | ESCALATED | RESOLVED | CLOSED
FIELD_VERIFICATION -> UNDER_REVIEW | ESCALATED | RESOLVED | CLOSED
ESCALATED -> UNDER_REVIEW | RESOLVED | CLOSED
RESOLVED -> CLOSED | UNDER_REVIEW
CLOSED -> (terminal)
```

Outcomes: VALID_ANOMALY, FALSE_POSITIVE, NEEDS_FIELD_VERIFICATION, ESCALATED,
NO_ISSUE_FOUND, DATA_ISSUE.

## Roles and scope

ADMIN, MINISTRY, STATE (own state), DISTRICT (own district), REVIEWER (assigned work or own
district), AUDITOR (read only plus audit trail). Scope is applied in SQL, so a district
officer cannot read another district's works even by calling the API directly. Reviewers
cannot change rules, weights or configuration.
