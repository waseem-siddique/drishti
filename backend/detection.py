"""Hybrid, explainable detection engine.

Layer 1 - deterministic rules encoded from MPLADS guidelines and public
          procurement red-flag literature.
Layer 2 - statistical outlier checks (robust z-score / IQR within peer group).
Layer 3 - unsupervised ensemble score (depth-based isolation scoring over
          engineered features, implemented in pure Python).

Every contribution carries a reason code, a human sentence and the evidence
values behind it, so no alert is a black box. Outputs are risk signals for
human review - never automated fraud verdicts.
"""

import json
import math
import random
import re
from datetime import date, datetime, timedelta, timezone

TODAY = date(2026, 9, 1)

STOPWORDS = {
    "of", "at", "for", "the", "and", "in", "to", "with", "near", "construction",
    "repair", "installation", "work", "works",
}

RULES = {
    "COST_OVERRUN": "Expenditure has exceeded the sanctioned estimate",
    "PAYMENT_WITHOUT_PROGRESS": "Money released is far ahead of physical progress",
    "STALLED_WORK": "No payment or progress update recorded for a long period",
    "SCHEDULE_OVERRUN": "Work is past its expected completion date and still open",
    "DUPLICATE_WORK": "A near-identical work exists in the same district",
    "SPENDING_BURST": "A single instalment covers most of the sanctioned amount",
    "COST_OUTLIER": "Sanctioned cost is an outlier against similar works",
    "RAPID_COMPLETION": "Work reported complete unusually fast for its category",
    "LOW_DATA_QUALITY": "Key fields are missing or inconsistent for this work",
    "ML_ANOMALY": "Combined pattern is unusual against the whole portfolio",
}

WEIGHTS = {
    "COST_OVERRUN": 26,
    "PAYMENT_WITHOUT_PROGRESS": 24,
    "STALLED_WORK": 18,
    "SCHEDULE_OVERRUN": 14,
    "DUPLICATE_WORK": 20,
    "SPENDING_BURST": 12,
    "COST_OUTLIER": 14,
    "RAPID_COMPLETION": 8,
    "LOW_DATA_QUALITY": 6,
    "ML_ANOMALY": 22,
}


def _d(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _tokens(name):
    return {
        t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t and t not in STOPWORDS
    }


def _median(values):
    values = sorted(values)
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def _mad(values, med):
    if not values:
        return 0.0
    return _median([abs(v - med) for v in values]) or 1e-9


def _severity(score):
    if score >= 75:
        return "critical"
    if score >= 55:
        return "high"
    if score >= 35:
        return "medium"
    return "low"


def _isolation_scores(feature_rows, rng, n_trees=60, sample_size=128):
    """Pure-python isolation-forest style anomaly score in [0, 1]."""
    keys = list(feature_rows.keys())
    if len(keys) < 8:
        return {k: 0.0 for k in keys}
    matrix = [feature_rows[k] for k in keys]
    dims = len(matrix[0])
    n = len(matrix)
    sample_size = min(sample_size, n)
    max_depth = math.ceil(math.log2(sample_size)) if sample_size > 1 else 1

    def build(points, depth):
        if depth >= max_depth or len(points) <= 1:
            return ("leaf", len(points))
        dim = rng.randrange(dims)
        values = [p[dim] for p in points]
        lo, hi = min(values), max(values)
        if lo == hi:
            return ("leaf", len(points))
        split = rng.uniform(lo, hi)
        left = [p for p in points if p[dim] < split]
        right = [p for p in points if p[dim] >= split]
        if not left or not right:
            return ("leaf", len(points))
        return ("node", dim, split, build(left, depth + 1), build(right, depth + 1))

    def c_factor(size):
        if size <= 1:
            return 1.0
        return 2 * (math.log(size - 1) + 0.5772156649) - (2 * (size - 1) / size)

    def path_length(tree, point, depth=0):
        if tree[0] == "leaf":
            return depth + c_factor(tree[1])
        _, dim, split, left, right = tree
        branch = left if point[dim] < split else right
        return path_length(branch, point, depth + 1)

    trees = [build(rng.sample(matrix, sample_size), 0) for _ in range(n_trees)]
    norm = c_factor(sample_size)
    scores = {}
    for key, point in zip(keys, matrix):
        avg = sum(path_length(t, point) for t in trees) / len(trees)
        scores[key] = 2 ** (-avg / norm)
    lows = sorted(scores.values())
    lo, hi = lows[0], lows[-1]
    span = (hi - lo) or 1.0
    return {k: (v - lo) / span for k, v in scores.items()}


SLA_DAYS = {"critical": 7, "high": 14, "medium": 30, "low": 45}
DEFAULT_THRESHOLDS = {"critical": 75, "high": 55, "medium": 35}


def default_policy():
    return {"weights": dict(WEIGHTS), "thresholds": dict(DEFAULT_THRESHOLDS), "sla_days": dict(SLA_DAYS)}


def get_policy(conn):
    """Return the active (latest published) risk policy, falling back to defaults."""
    try:
        row = conn.execute("SELECT policy FROM policy_versions ORDER BY id DESC LIMIT 1").fetchone()
    except Exception:  # table may not exist yet
        row = None
    policy = default_policy()
    if row:
        stored = json.loads(row["policy"])
        policy["weights"].update(stored.get("weights", {}))
        policy["thresholds"].update(stored.get("thresholds", {}))
        policy["sla_days"].update(stored.get("sla_days", {}))
    return policy


def severity_for(score, thresholds=None):
    t = thresholds or DEFAULT_THRESHOLDS
    if score >= t["critical"]:
        return "critical"
    if score >= t["high"]:
        return "high"
    if score >= t["medium"]:
        return "medium"
    return "low"


def compose(reasons, completeness, policy):
    """Combine weighted reason impacts into (score, severity). Mutates contributions."""
    weights = policy["weights"]
    raw = sum(float(weights.get(r["code"], 0)) * r["impact"] for r in reasons)
    score = round(min(99.0, 100 * (1 - math.exp(-raw / 45))), 1) if raw > 0 else 0.0
    for r in reasons:
        contribution = float(weights.get(r["code"], 0)) * r["impact"]
        r["contribution"] = round(contribution / raw * 100, 1) if raw else 0.0
    reasons.sort(key=lambda r: -r["contribution"])
    if completeness < 0.6:
        score = round(score * 0.9, 1)
    return score, severity_for(score, policy["thresholds"])


def _age_days(work_id):
    """Deterministic 0-20 day age so the demo queue has realistic SLA ageing."""
    return sum(ord(c) for c in work_id) % 21


def run_detection(conn):
    works = [dict(r) for r in conn.execute("SELECT * FROM works").fetchall()]
    payments = [dict(r) for r in conn.execute("SELECT * FROM payments ORDER BY pay_date").fetchall()]
    progress = [
        dict(r) for r in conn.execute("SELECT * FROM progress_updates ORDER BY update_date").fetchall()
    ]

    pay_by_work, prog_by_work = {}, {}
    for p in payments:
        pay_by_work.setdefault(p["work_id"], []).append(p)
    for p in progress:
        prog_by_work.setdefault(p["work_id"], []).append(p)

    # peer statistics per category
    by_category = {}
    for w in works:
        by_category.setdefault(w["category"], []).append(w)
    cat_stats = {}
    for cat, rows in by_category.items():
        amounts = [float(r["sanction_amount"] or 0) for r in rows]
        med = _median(amounts)
        cat_stats[cat] = {"median": med, "mad": _mad(amounts, med)}

    # duplicate detection within district + category
    dup_partner = {}
    buckets = {}
    for w in works:
        buckets.setdefault((w["state"], w["district"], w["category"]), []).append(w)
    for group in buckets.values():
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                ta, tb = _tokens(a["work_name"]), _tokens(b["work_name"])
                if not ta or not tb:
                    continue
                jaccard = len(ta & tb) / len(ta | tb)
                amt_a = float(a["sanction_amount"] or 0)
                amt_b = float(b["sanction_amount"] or 0)
                closeness = 1 - abs(amt_a - amt_b) / max(amt_a, amt_b, 1)
                if jaccard >= 0.8 and closeness >= 0.85:
                    dup_partner.setdefault(a["work_id"], []).append((b["work_id"], jaccard))
                    dup_partner.setdefault(b["work_id"], []).append((a["work_id"], jaccard))

    # engineered features for the unsupervised layer
    features = {}
    for w in works:
        sanction = float(w["sanction_amount"] or 0) or 1.0
        expenditure = float(w["expenditure"] or 0)
        prog = float(w["physical_progress"] or 0)
        s_date = _d(w["sanction_date"]) or TODAY
        exp_date = _d(w["expected_completion"]) or TODAY
        planned = max((exp_date - s_date).days, 1)
        elapsed = max((TODAY - s_date).days, 0)
        pays = pay_by_work.get(w["work_id"], [])
        last_activity = max(
            [_d(p["pay_date"]) for p in pays] + [_d(p["update_date"]) for p in prog_by_work.get(w["work_id"], [])]
            or [s_date],
            default=s_date,
        ) or s_date
        features[w["work_id"]] = [
            expenditure / sanction,
            prog / 100.0,
            (expenditure / sanction) - (prog / 100.0),
            elapsed / planned,
            (TODAY - last_activity).days / 365.0,
            math.log10(max(sanction, 1)),
            (max(p["amount"] for p in pays) / sanction) if pays else 0.0,
            float(w["completeness"] or 1.0),
        ]

    ml_scores = _isolation_scores(features, random.Random(26102))

    policy = get_policy(conn)
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    # carry case ownership, status and history across re-runs (a real case system never loses work)
    previous = {r["work_id"]: dict(r) for r in conn.execute(
        "SELECT id, work_id, status, assignee, created_at FROM alerts").fetchall()}
    conn.commit()
    conn.execute("PRAGMA foreign_keys = OFF")  # must be set outside a transaction
    conn.execute("UPDATE alert_actions SET alert_id = -alert_id")
    conn.execute("UPDATE feedback SET alert_id = -alert_id")
    conn.execute("DELETE FROM alerts")

    created = 0
    for w in works:
        wid = w["work_id"]
        sanction = float(w["sanction_amount"] or 0) or 1.0
        estimate = float(w["estimate_amount"] or 0) or sanction
        expenditure = float(w["expenditure"] or 0)
        prog = float(w["physical_progress"] or 0)
        pays = pay_by_work.get(wid, [])
        s_date = _d(w["sanction_date"]) or TODAY
        exp_date = _d(w["expected_completion"])
        completeness = float(w["completeness"] or 1.0)
        last_activity = max(
            [_d(p["pay_date"]) for p in pays]
            + [_d(p["update_date"]) for p in prog_by_work.get(wid, [])]
            or [s_date]
        ) or s_date
        idle_days = (TODAY - last_activity).days

        reasons = []

        overrun_pct = (expenditure - estimate) / estimate * 100 if estimate else 0
        if overrun_pct > 10:
            reasons.append(
                {
                    "code": "COST_OVERRUN",
                    "label": RULES["COST_OVERRUN"],
                    "detail": f"Expenditure is {overrun_pct:.1f}% above the sanctioned estimate",
                    "impact": min(1.0, overrun_pct / 60),
                    "layer": "rule",
                }
            )

        gap = (expenditure / sanction * 100) - prog
        if gap > 30 and prog < 70:
            reasons.append(
                {
                    "code": "PAYMENT_WITHOUT_PROGRESS",
                    "label": RULES["PAYMENT_WITHOUT_PROGRESS"],
                    "detail": f"{expenditure / sanction * 100:.0f}% of funds released against {prog:.0f}% physical progress",
                    "impact": min(1.0, gap / 70),
                    "layer": "rule",
                }
            )

        if idle_days > 180 and prog < 99.5:
            reasons.append(
                {
                    "code": "STALLED_WORK",
                    "label": RULES["STALLED_WORK"],
                    "detail": f"No payment or progress entry for {idle_days} days",
                    "impact": min(1.0, idle_days / 540),
                    "layer": "rule",
                }
            )

        if exp_date and TODAY > exp_date and prog < 99.5:
            delay = (TODAY - exp_date).days
            reasons.append(
                {
                    "code": "SCHEDULE_OVERRUN",
                    "label": RULES["SCHEDULE_OVERRUN"],
                    "detail": f"{delay} days past the expected completion date at {prog:.0f}% progress",
                    "impact": min(1.0, delay / 400),
                    "layer": "rule",
                }
            )

        if wid in dup_partner:
            partners = sorted(dup_partner[wid], key=lambda x: -x[1])
            reasons.append(
                {
                    "code": "DUPLICATE_WORK",
                    "label": RULES["DUPLICATE_WORK"],
                    "detail": "Near-identical scope and amount as " + ", ".join(p[0] for p in partners[:3]),
                    "impact": min(1.0, partners[0][1]),
                    "layer": "rule",
                    "links": [p[0] for p in partners[:3]],
                }
            )

        if pays:
            biggest = max(pays, key=lambda p: p["amount"])
            share = biggest["amount"] / sanction
            if share > 0.6:
                reasons.append(
                    {
                        "code": "SPENDING_BURST",
                        "label": RULES["SPENDING_BURST"],
                        "detail": f"Single instalment of Rs {biggest['amount']:,.0f} equals {share * 100:.0f}% of sanction",
                        "impact": min(1.0, share),
                        "layer": "rule",
                    }
                )

        stats = cat_stats.get(w["category"], {"median": sanction, "mad": 1.0})
        rz = 0.6745 * (sanction - stats["median"]) / (stats["mad"] or 1e-9)
        if rz > 3.5:
            reasons.append(
                {
                    "code": "COST_OUTLIER",
                    "label": RULES["COST_OUTLIER"],
                    "detail": f"Sanction is {sanction / max(stats['median'], 1):.1f}x the median for {w['category']}",
                    "impact": min(1.0, rz / 10),
                    "layer": "statistical",
                }
            )

        actual = _d(w["actual_completion"])
        if actual and exp_date:
            taken = (actual - s_date).days
            planned = max((exp_date - s_date).days, 1)
            if taken < planned * 0.35:
                reasons.append(
                    {
                        "code": "RAPID_COMPLETION",
                        "label": RULES["RAPID_COMPLETION"],
                        "detail": f"Completed in {taken} days against a planned {planned} days",
                        "impact": 0.6,
                        "layer": "statistical",
                    }
                )

        if completeness < 0.6:
            reasons.append(
                {
                    "code": "LOW_DATA_QUALITY",
                    "label": RULES["LOW_DATA_QUALITY"],
                    "detail": f"Record completeness is only {completeness * 100:.0f}% - review before acting",
                    "impact": 1 - completeness,
                    "layer": "data quality",
                }
            )

        ml = ml_scores.get(wid, 0.0)
        if ml > 0.55:
            reasons.append(
                {
                    "code": "ML_ANOMALY",
                    "label": RULES["ML_ANOMALY"],
                    "detail": f"Isolation score {ml:.2f} - spend, progress and timeline pattern is rare in the portfolio",
                    "impact": ml,
                    "layer": "model",
                }
            )

        if not reasons:
            continue

        score, severity = compose(reasons, completeness, policy)
        confidence = round(min(1.0, completeness * (0.75 + 0.25 * min(len(reasons), 4) / 4)), 2)
        raised = now_dt - timedelta(days=_age_days(wid), hours=_age_days(wid[::-1]))
        due = raised + timedelta(days=policy["sla_days"][severity])

        evidence = {
            "sanction_amount": sanction,
            "estimate_amount": estimate,
            "expenditure": expenditure,
            "utilisation_pct": round(expenditure / sanction * 100, 1),
            "physical_progress": prog,
            "idle_days": idle_days,
            "payment_count": len(pays),
            "largest_payment": max([p["amount"] for p in pays], default=0),
            "category_median_sanction": round(stats["median"], 2),
            "completeness": completeness,
            "timeline": [
                {"date": w["recommended_date"], "event": "Work recommended by MP"},
                {"date": w["sanction_date"], "event": f"Sanctioned for Rs {sanction:,.0f}"},
            ]
            + [
                {
                    "date": p["pay_date"],
                    "event": f"Payment of Rs {p['amount']:,.0f} ({p['voucher']}) at {p['progress_at_payment']:.0f}% progress",
                }
                for p in pays
            ]
            + (
                [{"date": w["actual_completion"], "event": "Reported complete"}]
                if w["actual_completion"]
                else [{"date": w["expected_completion"], "event": "Expected completion (planned)"}]
            ),
        }

        conn.execute(
            "INSERT INTO alerts (work_id, risk_score, severity, reason_codes, evidence,"
            " confidence, status, created_at, updated_at, due_at, assignee) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                wid,
                score,
                severity,
                json.dumps(reasons),
                json.dumps(evidence),
                confidence,
                "open",
                raised.isoformat(),
                raised.isoformat(),
                due.isoformat(),
                None,
            ),
        )
        old = previous.get(wid)
        if old:
            new_id = conn.execute("SELECT last_insert_rowid() AS i").fetchone()["i"]
            old_raised = datetime.fromisoformat(old["created_at"])
            if old_raised.tzinfo is None:
                old_raised = old_raised.replace(tzinfo=timezone.utc)
            conn.execute(
                "UPDATE alerts SET status = ?, assignee = ?, created_at = ?, due_at = ? WHERE id = ?",
                (old["status"], old["assignee"], old_raised.isoformat(),
                 (old_raised + timedelta(days=policy["sla_days"][severity])).isoformat(), new_id),
            )
            conn.execute("UPDATE alert_actions SET alert_id = ? WHERE alert_id = ?", (new_id, -old["id"]))
            conn.execute("UPDATE feedback SET alert_id = ? WHERE alert_id = ?", (new_id, -old["id"]))
        created += 1

    conn.execute("DELETE FROM alert_actions WHERE alert_id < 0")
    conn.execute("DELETE FROM feedback WHERE alert_id < 0")
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    return created
