# DRISHTI — architecture notes

**PS 26102** · *Development of an AI-powered system to detect anomalies, fraud, and inefficiencies in
MPLAD Scheme implementation* · MoSPI (DIID) · Team Syntrix · SIH 2026

## 1. Chosen approach: hybrid explainable system

Pure rules are transparent but rigid; a pure ML model is flexible but unexplainable — and an
unexplainable accusation is useless to a district officer. DRISHTI therefore combines both and
**always ships the explanation with the score**.

```
Data sources            Processing              Detection engine         Risk & explanation      Human action
---------------         ----------              ----------------         ------------------      ------------
sanctions   \           ingest + clean          rule layer               weighted risk score     ranked queue
payments     >--------> entity matching  -----> statistical layer -----> reason codes      ----> case review
progress    /           feature building        anomaly model            evidence timeline       action + feedback
completion              data-quality score      (isolation-style)        confidence              audit log
```

Nine steps end to end: collect → clean → match into one case per work → rules → statistics + model
→ risk score → explain → dashboard → officer action and feedback (which feeds threshold retuning).

## 2. Components

| Layer | File | Responsibility |
| --- | --- | --- |
| Storage | `backend/db.py` | SQLite schema: `users, works, payments, progress_updates, alerts, alert_actions, feedback, audit_log` + indexes |
| Identity | `backend/auth.py` | PBKDF2-HMAC-SHA256 password hashing (120k rounds), HMAC-signed session tokens (12 h TTL), jurisdiction `scope_filter()` compiled into every SQL query |
| Data | `backend/seed.py` | Deterministic synthetic dataset (seed 26102): 6 states, 23 districts, 8 categories, 10 MPs, agency types, injected anomalies and duplicate/split works; also writes CSV extracts to `data/` |
| Engine | `backend/detection.py` | Feature building, rule layer, robust statistics, pure-Python isolation-forest scoring, score composition and explanation objects |
| API | `backend/app.py` | `ThreadingHTTPServer` JSON API, SPA static hosting, security headers, bootstrap/seeding, CLI flags |
| UI | `frontend/*` | Vanilla SPA: hash router, API client, seven views, SVG charts, theme system |

No third-party runtime dependency anywhere — deliberate, so the prototype runs on an air-gapped
evaluation machine with only Python installed.

## 3. Feature set used for scoring

Per work: utilisation ratio (expenditure / sanction), utilisation-minus-progress gap, cost variance
against estimate, cost per unit against category peers, idle days since last progress update,
instalment count and burst shape, schedule slippage against expected completion, name/amount
similarity with sibling works in the same district and category, and a data-completeness score.

## 4. Scoring and severity

```
raw   = sum(weight_i)  for every fired signal i
score = min(99, 100 * (1 - exp(-raw / 45)))
```

Diminishing returns prevent one work with many small flags from outranking a single severe,
high-value case. Weights: `COST_OVERRUN 26 · PAYMENT_WITHOUT_PROGRESS 24 · ML_ANOMALY 22 ·
DUPLICATE_WORK 20 · STALLED_WORK 18 · SCHEDULE_OVERRUN 14 · COST_OUTLIER 14 · SPENDING_BURST 12 ·
RAPID_COMPLETION 8 · LOW_DATA_QUALITY 6`.

Severity bands: **critical ≥ 75**, **high ≥ 55**, **medium ≥ 35**, otherwise **low**.
Confidence is reduced proportionally to missing fields, and low completeness raises its own reason
code instead of being silently absorbed.

## 5. Explainability contract

1. Every alert lists its reason codes with a **percentage contribution** to the score.
2. Every reason states the concrete figures that fired it (amounts, dates, percentages).
3. Every case carries an **evidence timeline** from recommendation to latest payment.
4. Confidence drops when the input data is weak; the record is surfaced for correction.
5. Officer feedback (*useful / not useful*) is stored against the alert for threshold and model
   retuning.
6. Wording throughout is “risk signal for review” — never a finding of fraud.

## 6. Security and governance

- Role-based row scoping (district → state → ministry) enforced server-side in SQL.
- Salted PBKDF2 password storage; signed, expiring bearer tokens.
- Immutable append-only `audit_log` for logins, alert decisions and detection runs.
- Parameterised SQL everywhere; static file serving is path-traversal guarded; `nosniff` and
  `Referrer-Policy` headers set on all responses.

## 7. Production path

| Prototype | Production |
| --- | --- |
| Synthetic seeded dataset | Scheduled ingestion from the MPLADS portal / MoSPI data warehouse |
| SQLite | PostgreSQL with row-level security |
| Stdlib HTTP server | FastAPI/Gunicorn behind NIC hosting, HTTPS, WAF |
| Local token auth | NIC SSO / eOffice identity, MFA for ministry roles |
| Pure-Python anomaly model | Trained ensemble with drift monitoring and periodic revalidation |
| Manual re-run | Nightly batch scoring plus event-triggered rescoring on new payments |

Measured accuracy, precision at top-K and officer time saved are to be established in a district
pilot; the prototype intentionally publishes no such numbers.
