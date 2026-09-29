<p align="center">
  <img src="frontend/assets/logo.png" alt="Team Syntrix" width="110" />
</p>

<h1 align="center">DRISHTI</h1>
<p align="center"><b>Explainable risk monitoring for MPLAD Scheme works</b><br/>
Smart India Hackathon 2026 &middot; PS 26102 &middot; MoSPI (Data Informatics &amp; Innovation Division) &middot; Team Syntrix</p>

---

## What this is

DRISHTI reads the records the MPLAD Scheme already produces — recommendations, sanctions, cost
estimates, payments, progress updates and completion reports — links them into **one case per work**,
scores every work for risk, and hands officials a **ranked queue with the reasons attached**.

It does not just show data; it helps officials decide what needs attention first.

> An alert is a **risk signal for human review** — never an automated finding of fraud.

## What's new in this version

- **Landing page** with the PS 26102 problem statement, MPLADS background, solution layers and workflow.
- **Case board** (drag-and-drop kanban) with **SLA timers**, breach and due-soon alerts, and owner assignment.
- **Case file drawer**: auto-written case brief, suggested next step, fund-flow view, timeline, threaded discussion with `@mentions`, activity log.
- **Policy studio** (ministry): tune reason weights, severity thresholds and SLA days, preview the impact (before/after, transition matrix, biggest movers), then publish a versioned policy that rescores every alert.
- **Accountability scorecards**: A-E grades for agencies, MPs and districts.
- **Watchlist**, **saved and shared views**, **bulk actions**, **CSV export**, **notification inbox**.
- **Command palette** (Ctrl/Cmd K) and keyboard shortcuts (`?` for the list).
- **Printable inspection memo** for field visits, plus light and dark themes.

## Design and layout

- Palette: `#F15025` orange, `#FFFFFF`, `#E6E8E6`, `#CED0CE`, `#191919`.
- Lucide icons (`frontend/icons.js`), serif and Inter type, light and dark themes.
- Fluid layout for phones, folded and unfolded foldables, tablets and desktops. Rotation and resizing keep your place: filters, open case, scroll and unsent drafts are restored.
- Effects: interactive dot grid, blur-in headings, spotlight cards, scroll reveal and a marquee (`frontend/fx.js`).

## How to run

1. Install Python 3.9 or newer (nothing else is needed).
2. Unzip the folder and open a terminal inside it.
3. Start the app:
   - Mac / Linux: `./run.sh`
   - Windows: `python backend/app.py`
4. Open http://127.0.0.1:8000 in your browser.
5. Press `Ctrl + C` in the terminal to stop it.

To reset the sample data, add `--reseed` (Windows) or run `./run.sh 8000 reseed` (Mac / Linux).

### Demo logins

| Username   | Password   | Sees                        |
| ---------- | ---------- | --------------------------- |
| `ministry` | `drishti` | All states (national view)  |
| `state`    | `drishti` | Maharashtra only            |
| `district` | `drishti` | Pune district only          |

Row-level scoping is enforced in SQL on the server, not hidden in the UI.

## Features

**Detection — three explainable layers**

| Layer | Signals |
| --- | --- |
| Rules | `COST_OVERRUN`, `PAYMENT_WITHOUT_PROGRESS`, `STALLED_WORK`, `SCHEDULE_OVERRUN`, `DUPLICATE_WORK`, `SPENDING_BURST` |
| Statistics | `COST_OUTLIER` (robust z-score / MAD against peer group), `RAPID_COMPLETION`, `LOW_DATA_QUALITY` |
| Model | `ML_ANOMALY` — isolation-forest style anomaly score over engineered features, implemented in pure Python |

Weighted signals are combined into a 0–99 risk score with severity bands
(critical ≥ 75, high ≥ 55, medium ≥ 35, else low). Every reason code carries its **percentage
contribution** to the final score, and confidence is damped when the source data is incomplete.

**Console**

- **Overview** — KPIs, spending trend, severity mix, top risk queue, reason-code distribution
- **Alert queue** — filter by severity, status, state, district, category and reason code; search; sort; paginate
- **Case detail drawer** — risk gauge, reason codes with contribution bars, evidence figures,
  evidence timeline, peer comparison, action buttons and officer feedback
- **Risk map** — district heat map (click a district to filter the queue)
- **Analytics** — detection mix, category risk, pipeline trend, recent officer actions
- **Data quality** — records too incomplete to score confidently, so districts can fix the source
- **Audit trail** — immutable log of every login, decision and detection run
- **Dark / light theme toggle** (remembered per browser, follows OS preference first)
- **Responsive from 320 px to ultrawide** — off-canvas navigation, tables that collapse into cards

## Project structure

```
drishti/
├── backend/
│   ├── app.py          # HTTP API + static server (stdlib only)
│   ├── auth.py         # PBKDF2 password hashing, signed tokens, jurisdiction scoping
│   ├── db.py           # SQLite schema, connection, audit log
│   ├── detection.py    # rules + statistics + anomaly model, scoring and explanations
│   └── seed.py         # deterministic synthetic MPLADS-shaped dataset
├── frontend/
│   ├── index.html      # app shell + login (logo embedded on every screen)
│   ├── styles.css      # design system, light/dark tokens, responsive layout
│   ├── app.js          # router, API client, all views
│   ├── charts.js       # dependency-free SVG charts
│   └── assets/logo.png # Syntrix logo (also the favicon)
├── data/               # generated SQLite DB + CSV extracts
├── docs/architecture.md
└── run.sh
```

## API reference

All `/api/*` routes except `health` and `auth/login` require `Authorization: Bearer <token>`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Liveness probe |
| POST | `/api/auth/login` | `{username, password}` → token + user |
| GET | `/api/me` | Current session |
| GET | `/api/summary` | KPIs, severity mix, districts, categories, reasons, trend, quality |
| GET | `/api/alerts` | Ranked alerts (`severity, status, state, district, category, code, q, sort, page, limit`) |
| GET | `/api/filters` | Filter option lists scoped to the user |
| GET | `/api/works/<work_id>` | Full case: work, alert, reasons, payments, progress, peers |
| GET | `/api/data-quality` | Records with low completeness |
| GET | `/api/audit` | Audit log |
| GET | `/api/actions` | Recent officer actions |
| POST | `/api/alerts/<id>/action` | `acknowledge` \| `assign_inspection` \| `seek_clarification` \| `escalate` \| `dismiss` |
| POST | `/api/alerts/<id>/feedback` | `{useful: true\|false}` |
| POST | `/api/detect/run` | Re-run detection (ministry / state roles) |

Example:

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"ministry","password":"drishti"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["token"])')

curl -s localhost:8000/api/summary -H "Authorization: Bearer $TOKEN"
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DRISHTI_SECRET` | dev fallback | HMAC key for session tokens — **set this in any real deployment** |
| `DRISHTI_VERBOSE` | unset | Print per-request access logs |

## Notes for evaluators

- The demo dataset is **synthetic and generated deterministically** (seed 26102), so every run
  produces the same cases and the same alerts — useful for a repeatable demo.
- No accuracy or savings percentages are claimed anywhere in the product; those must come from a
  measured pilot on real MPLADS data.
- Detection is fully re-runnable from the UI (**Run detection**), which rewrites alerts while
  preserving the audit trail.

© 2026 Team Syntrix. Built for Smart India Hackathon 2026.
