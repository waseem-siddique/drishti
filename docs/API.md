# API reference

Base URL `/api`. All endpoints except `/health` and `/auth/login` require
`Authorization: Bearer <token>`.

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/health` | public |
| POST | `/auth/login` | public |
| POST | `/auth/logout` | authenticated |
| GET | `/me` | authenticated |
| GET | `/works` | works:read |
| GET | `/works/filters` | works:read |
| GET | `/works/{work_ref}` | works:read |
| GET | `/works/{work_ref}/risk` | risk:read |
| POST | `/works/{work_ref}/evidence` | evidence:upload |
| GET / POST | `/cases` | cases:read / cases:create |
| GET | `/cases/{case_ref}` | cases:read |
| PATCH | `/cases/{case_ref}/status` | cases:update |
| POST | `/cases/{case_ref}/assign` | cases:assign |
| POST | `/cases/{case_ref}/outcome` | cases:outcome |
| POST | `/cases/{case_ref}/notes` | cases:update |
| PATCH | `/cases/{case_ref}/checklist` | cases:update |
| POST | `/cases/{case_ref}/evidence` | evidence:upload |
| GET | `/verification/workspace` | cases:read |
| GET | `/dashboard/summary`, `/dashboard/risk-distribution`, `/dashboard/trends` | analytics:read |
| GET | `/analytics/categories`, `/analytics/geography`, `/analytics/outcomes`, `/analytics/case-load` | analytics:read |
| GET | `/data-quality` | quality:read |
| GET | `/risk/rules`, `/risk/signals` | risk:read |
| POST | `/risk/analyze` | risk:analyse |
| POST | `/risk/explain` | risk:read |
| POST | `/ingestion/upload` | ingestion:upload |
| GET | `/ingestion/jobs`, `/ingestion/jobs/{id}` | quality:read |
| GET | `/notifications`; PATCH `/notifications/{id}/read` | notifications:read |
| GET | `/search?q=` | authenticated |
| GET | `/integrations` | authenticated |
| GET / POST | `/admin/users`; PATCH `/admin/users/{id}` | admin:users |
| PATCH | `/admin/rules/{rule_id}` | admin:rules |
| GET | `/admin/config`; PATCH `/admin/config/{key}` | admin:config |
| GET | `/admin/audit` | audit:read |

Errors return `{"detail": "..."}` with a message written for the person reading it, for
example `Your role (Reviewer) cannot perform this action.`
