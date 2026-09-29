"""Case-management layer for DRISHTI.

Everything an officer team needs to *work* the alert queue, not just read it:
ownership and SLAs, a status board, threaded case discussion with @mentions,
a per-user watchlist, saved queue views, an inbox of notifications,
accountability scorecards and a versioned risk-policy studio with a what-if
simulator. Standard library only.
"""

import json
import random
import re
from datetime import datetime, timedelta, timezone

import auth
import db
import detection

STATUSES = ["open", "in_review", "actioned", "dismissed"]
SEVERITIES = ["critical", "high", "medium", "low"]
MENTION_RE = re.compile(r"@([a-z0-9._-]+)", re.I)


def now_dt():
    return datetime.now(timezone.utc).replace(microsecond=0)


def now_iso():
    return now_dt().isoformat()


def _dict(row):
    return {k: row[k] for k in row.keys()}


def _parse(ts):
    try:
        dt = datetime.fromisoformat(str(ts))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def sla_state(due_at, status):
    """Return (state, hours_left) where state is breached | due_soon | on_track | closed."""
    if status in ("actioned", "dismissed"):
        return "closed", None
    due = _parse(due_at)
    if not due:
        return "on_track", None
    hours = (due - now_dt()).total_seconds() / 3600
    if hours < 0:
        return "breached", round(hours)
    if hours < 72:
        return "due_soon", round(hours)
    return "on_track", round(hours)


def notify(conn, username, kind, title, body=None, work_id=None):
    conn.execute(
        "INSERT INTO notifications (username, kind, title, body, work_id, created_at) VALUES (?,?,?,?,?,?)",
        (username, kind, title, body, work_id, now_iso()),
    )


def user_names(conn):
    return {r["username"]: r["full_name"] for r in conn.execute("SELECT username, full_name FROM users")}


# ---------------------------------------------------------------------------
# Users / assignment
# ---------------------------------------------------------------------------

def assignable_users(conn, user):
    rows = conn.execute(
        "SELECT username, full_name, role, scope_state, scope_district FROM users ORDER BY role, full_name"
    ).fetchall()
    out = []
    for r in rows:
        # an officer can hand work to people at their level of jurisdiction or wider
        if user["role"] == "district" and r["role"] == "district" and r["scope_district"] != user.get("district"):
            continue
        if user["role"] == "state" and r["role"] in ("state", "district") and r["scope_state"] != user.get("state"):
            continue
        out.append({
            "username": r["username"], "name": r["full_name"], "role": r["role"],
            "state": r["scope_state"], "district": r["scope_district"],
        })
    return out


def _alert_in_scope(conn, user, alert_id):
    scope_sql, scope_args = auth.scope_filter(user)
    row = conn.execute(
        f"""SELECT a.*, w.work_name FROM alerts a JOIN works w ON w.work_id = a.work_id
            WHERE a.id = ? AND {scope_sql}""",
        [alert_id] + scope_args,
    ).fetchone()
    return row


def assign(conn, user, alert_id, assignee):
    alert = _alert_in_scope(conn, user, alert_id)
    if not alert:
        return None
    names = user_names(conn)
    if assignee and assignee not in names:
        raise ValueError("Unknown assignee")
    status = alert["status"]
    if assignee and status == "open":
        status = "in_review"
    conn.execute(
        "UPDATE alerts SET assignee = ?, status = ?, updated_at = ? WHERE id = ?",
        (assignee or None, status, now_iso(), alert_id),
    )
    note = f"Assigned to {names.get(assignee, assignee)}" if assignee else "Unassigned"
    conn.execute(
        "INSERT INTO alert_actions (alert_id, username, action, note, created_at) VALUES (?,?,?,?,?)",
        (alert_id, user["sub"], "assign", note, now_iso()),
    )
    if assignee and assignee != user["sub"]:
        notify(conn, assignee, "assignment", f"{user['name']} assigned you a case",
               alert["work_name"], alert["work_id"])
    conn.commit()
    db.log_audit(conn, user["sub"], "alert.assign", alert["work_id"], note)
    return {"ok": True, "status": status, "assignee": assignee}


def set_status(conn, user, alert_id, status, note=""):
    if status not in STATUSES:
        raise ValueError("Unsupported status")
    alert = _alert_in_scope(conn, user, alert_id)
    if not alert:
        return None
    conn.execute("UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?", (status, now_iso(), alert_id))
    conn.execute(
        "INSERT INTO alert_actions (alert_id, username, action, note, created_at) VALUES (?,?,?,?,?)",
        (alert_id, user["sub"], "move_" + status, note or f"Moved to {status.replace('_', ' ')}", now_iso()),
    )
    if status == "actioned":
        for r in conn.execute("SELECT username FROM users WHERE role = 'ministry'").fetchall():
            if r["username"] != user["sub"]:
                notify(conn, r["username"], "escalation", "Case escalated for ministry review",
                       alert["work_name"], alert["work_id"])
    conn.commit()
    db.log_audit(conn, user["sub"], f"alert.move.{status}", alert["work_id"], note)
    return {"ok": True, "status": status}


def board(conn, user, params):
    scope_sql, scope_args = auth.scope_filter(user)
    where, args = [scope_sql], list(scope_args)
    mine = params.get("mine", [""])[0]
    if mine == "1":
        where.append("a.assignee = ?")
        args.append(user["sub"])
    sev = params.get("severity", [""])[0]
    if sev in SEVERITIES:
        where.append("a.severity = ?")
        args.append(sev)
    rows = conn.execute(
        f"""SELECT a.id, a.work_id, a.risk_score, a.severity, a.status, a.assignee, a.due_at,
                   a.reason_codes, a.updated_at, w.work_name, w.district, w.state, w.sanction_amount,
                   (SELECT COUNT(*) FROM comments c WHERE c.work_id = a.work_id) AS comments
            FROM alerts a JOIN works w ON w.work_id = a.work_id
            WHERE {' AND '.join(where)}
            ORDER BY a.risk_score DESC""",
        args,
    ).fetchall()
    names = user_names(conn)
    columns = {s: [] for s in STATUSES}
    totals = {s: 0 for s in STATUSES}
    for r in rows:
        item = _dict(r)
        reasons = json.loads(item.pop("reason_codes"))
        item["top_reason"] = reasons[0]["code"] if reasons else None
        item["assignee_name"] = names.get(item["assignee"]) if item["assignee"] else None
        item["sla"], item["sla_hours"] = sla_state(item["due_at"], item["status"])
        totals[item["status"]] += 1
        if len(columns[item["status"]]) < 60:
            columns[item["status"]].append(item)
    return {"columns": columns, "totals": totals}


def sla_summary(conn, user):
    scope_sql, scope_args = auth.scope_filter(user)
    rows = conn.execute(
        f"""SELECT a.due_at, a.status, a.severity, a.assignee FROM alerts a
            JOIN works w ON w.work_id = a.work_id WHERE {scope_sql}""",
        scope_args,
    ).fetchall()
    out = {"breached": 0, "due_soon": 0, "on_track": 0, "closed": 0,
           "unassigned_critical": 0, "mine": 0, "mine_breached": 0}
    for r in rows:
        state, _ = sla_state(r["due_at"], r["status"])
        out[state] += 1
        if r["severity"] == "critical" and not r["assignee"] and r["status"] == "open":
            out["unassigned_critical"] += 1
        if r["assignee"] == user["sub"] and state != "closed":
            out["mine"] += 1
            if state == "breached":
                out["mine_breached"] += 1
    active = out["breached"] + out["due_soon"] + out["on_track"]
    out["compliance_pct"] = round((1 - out["breached"] / active) * 100, 1) if active else 100.0
    return out


# ---------------------------------------------------------------------------
# Discussion, watchlist, saved views, notifications
# ---------------------------------------------------------------------------

def comments(conn, work_id):
    names = user_names(conn)
    rows = conn.execute("SELECT * FROM comments WHERE work_id = ? ORDER BY id", (work_id,)).fetchall()
    return [dict(_dict(r), name=names.get(r["username"], r["username"])) for r in rows]


def add_comment(conn, user, work_id, body):
    body = (body or "").strip()[:2000]
    if not body:
        raise ValueError("Comment cannot be empty")
    conn.execute(
        "INSERT INTO comments (work_id, username, body, created_at) VALUES (?,?,?,?)",
        (work_id, user["sub"], body, now_iso()),
    )
    known = user_names(conn)
    work = conn.execute("SELECT work_name FROM works WHERE work_id = ?", (work_id,)).fetchone()
    for handle in {m.lower() for m in MENTION_RE.findall(body)}:
        if handle in known and handle != user["sub"]:
            notify(conn, handle, "mention", f"{user['name']} mentioned you",
                   (work["work_name"] if work else work_id) + " - " + body[:120], work_id)
    for r in conn.execute("SELECT username FROM watchlist WHERE work_id = ?", (work_id,)).fetchall():
        if r["username"] != user["sub"]:
            notify(conn, r["username"], "watch", "New comment on a watched work",
                   body[:140], work_id)
    conn.commit()
    db.log_audit(conn, user["sub"], "case.comment", work_id, body[:120])
    return comments(conn, work_id)


def watchlist(conn, user):
    scope_sql, scope_args = auth.scope_filter(user)
    rows = conn.execute(
        f"""SELECT w.work_id, w.work_name, w.district, w.state, w.category, w.sanction_amount,
                   w.expenditure, w.physical_progress, wl.created_at AS watched_at,
                   a.id AS alert_id, a.risk_score, a.severity, a.status, a.due_at, a.assignee
            FROM watchlist wl JOIN works w ON w.work_id = wl.work_id
            LEFT JOIN alerts a ON a.work_id = w.work_id
            WHERE wl.username = ? AND {scope_sql} ORDER BY COALESCE(a.risk_score, 0) DESC""",
        [user["sub"]] + scope_args,
    ).fetchall()
    items = []
    for r in rows:
        item = _dict(r)
        item["sla"], item["sla_hours"] = sla_state(item["due_at"], item["status"])
        items.append(item)
    return items


def toggle_watch(conn, user, work_id):
    exists = conn.execute(
        "SELECT 1 FROM watchlist WHERE username = ? AND work_id = ?", (user["sub"], work_id)
    ).fetchone()
    if exists:
        conn.execute("DELETE FROM watchlist WHERE username = ? AND work_id = ?", (user["sub"], work_id))
        watching = False
    else:
        conn.execute("INSERT INTO watchlist VALUES (?,?,?)", (user["sub"], work_id, now_iso()))
        watching = True
    conn.commit()
    return {"watching": watching}


def watched_ids(conn, user):
    return [r["work_id"] for r in conn.execute("SELECT work_id FROM watchlist WHERE username = ?", (user["sub"],))]


def saved_views(conn, user):
    rows = conn.execute(
        "SELECT * FROM saved_views WHERE username = ? OR shared = 1 ORDER BY id", (user["sub"],)
    ).fetchall()
    return [dict(_dict(r), filters=json.loads(r["filters"]), mine=r["username"] == user["sub"]) for r in rows]


def save_view(conn, user, name, filters, shared):
    name = (name or "").strip()[:60]
    if not name:
        raise ValueError("View needs a name")
    clean = {k: v for k, v in (filters or {}).items()
             if k in ("severity", "status", "state", "district", "category", "code", "q", "sort", "sla", "assignee")}
    conn.execute(
        "INSERT INTO saved_views (username, name, filters, shared, created_at) VALUES (?,?,?,?,?)",
        (user["sub"], name, json.dumps(clean), 1 if shared else 0, now_iso()),
    )
    conn.commit()
    return saved_views(conn, user)


def delete_view(conn, user, view_id):
    conn.execute("DELETE FROM saved_views WHERE id = ? AND username = ?", (view_id, user["sub"]))
    conn.commit()
    return saved_views(conn, user)


def notifications(conn, user):
    rows = conn.execute(
        "SELECT * FROM notifications WHERE username = ? ORDER BY id DESC LIMIT 40", (user["sub"],)
    ).fetchall()
    unread = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE username = ? AND read_at IS NULL", (user["sub"],)
    ).fetchone()["c"]
    return {"items": [_dict(r) for r in rows], "unread": unread, "sla": sla_summary(conn, user)}


def mark_read(conn, user, ids=None):
    if ids:
        marks = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE notifications SET read_at = ? WHERE username = ? AND id IN ({marks})",
            [now_iso(), user["sub"]] + [int(i) for i in ids],
        )
    else:
        conn.execute(
            "UPDATE notifications SET read_at = ? WHERE username = ? AND read_at IS NULL", (now_iso(), user["sub"])
        )
    conn.commit()
    return notifications(conn, user)


# ---------------------------------------------------------------------------
# Accountability scorecards
# ---------------------------------------------------------------------------

def _grade(index):
    for limit, grade in ((10, "A"), (20, "B"), (32, "C"), (45, "D")):
        if index < limit:
            return grade
    return "E"


def scorecards(conn, user, by):
    group = {"agency": "w.agency", "mp": "w.mp_name", "district": "w.district"}.get(by)
    if not group:
        raise ValueError("by must be agency, mp or district")
    scope_sql, scope_args = auth.scope_filter(user)
    rows = conn.execute(
        f"""SELECT {group} AS entity, MIN(w.state) AS state, MIN(w.house) AS house,
                   COUNT(*) AS works,
                   SUM(w.sanction_amount) AS sanctioned,
                   SUM(w.expenditure) AS spent,
                   AVG(w.physical_progress) AS avg_progress,
                   AVG(w.completeness) AS completeness,
                   COUNT(a.id) AS alerts,
                   SUM(CASE WHEN a.severity IN ('critical','high') THEN 1 ELSE 0 END) AS serious,
                   SUM(COALESCE(a.risk_score, 0)) / COUNT(*) AS risk_index,
                   SUM(CASE WHEN a.severity IN ('critical','high') THEN w.sanction_amount ELSE 0 END) AS exposure,
                   SUM(CASE WHEN a.reason_codes LIKE '%COST_OVERRUN%' THEN 1 ELSE 0 END) AS overruns,
                   SUM(CASE WHEN a.reason_codes LIKE '%STALLED_WORK%' THEN 1 ELSE 0 END) AS stalled,
                   SUM(CASE WHEN a.status IN ('actioned','dismissed') THEN 1 ELSE 0 END) AS resolved
            FROM works w LEFT JOIN alerts a ON a.work_id = w.work_id
            WHERE {scope_sql} GROUP BY entity HAVING works >= 3
            ORDER BY risk_index DESC""",
        scope_args,
    ).fetchall()
    items = []
    for r in rows:
        item = _dict(r)
        item["risk_index"] = round(item["risk_index"] or 0, 1)
        item["grade"] = _grade(item["risk_index"])
        item["alert_rate"] = round(item["alerts"] / item["works"] * 100, 1)
        item["resolution_rate"] = round(item["resolved"] / item["alerts"] * 100, 1) if item["alerts"] else 100.0
        item["utilisation"] = round((item["spent"] or 0) / (item["sanctioned"] or 1) * 100, 1)
        items.append(item)
    avg = round(sum(i["risk_index"] for i in items) / len(items), 1) if items else 0
    return {"by": by, "items": items, "portfolio_avg": avg}


# ---------------------------------------------------------------------------
# Risk policy studio
# ---------------------------------------------------------------------------

def _clean_policy(data):
    policy = detection.default_policy()
    for code, value in (data.get("weights") or {}).items():
        if code in policy["weights"]:
            policy["weights"][code] = max(0.0, min(60.0, float(value)))
    for band, value in (data.get("thresholds") or {}).items():
        if band in policy["thresholds"]:
            policy["thresholds"][band] = max(1.0, min(99.0, float(value)))
    t = policy["thresholds"]
    if not (t["critical"] > t["high"] > t["medium"]):
        raise ValueError("Thresholds must satisfy critical > high > medium")
    for band, value in (data.get("sla_days") or {}).items():
        if band in policy["sla_days"]:
            policy["sla_days"][band] = int(max(1, min(180, float(value))))
    return policy


def policy_state(conn):
    versions = [
        dict(_dict(r), policy=json.loads(r["policy"]))
        for r in conn.execute("SELECT * FROM policy_versions ORDER BY id DESC LIMIT 20").fetchall()
    ]
    return {
        "active": detection.get_policy(conn),
        "defaults": detection.default_policy(),
        "versions": versions,
        "rules": [{"code": k, "label": v} for k, v in detection.RULES.items()],
    }


def _rescore(conn, policy):
    rows = conn.execute(
        """SELECT a.id, a.work_id, a.risk_score, a.severity, a.reason_codes, a.status, a.created_at,
                  w.work_name, w.district, w.sanction_amount, w.completeness
           FROM alerts a JOIN works w ON w.work_id = a.work_id"""
    ).fetchall()
    out = []
    for r in rows:
        reasons = json.loads(r["reason_codes"])
        score, sev = detection.compose(reasons, float(r["completeness"] or 1.0), policy)
        out.append((r, reasons, score, sev))
    return out


def simulate(conn, data):
    policy = _clean_policy(data)
    results = _rescore(conn, policy)
    matrix = {a: {b: 0 for b in SEVERITIES} for a in SEVERITIES}
    before = {s: 0 for s in SEVERITIES}
    after = {s: 0 for s in SEVERITIES}
    exp_before = exp_after = 0.0
    movers = []
    for r, _, score, sev in results:
        before[r["severity"]] += 1
        after[sev] += 1
        matrix[r["severity"]][sev] += 1
        amount = float(r["sanction_amount"] or 0)
        if r["severity"] in ("critical", "high"):
            exp_before += amount
        if sev in ("critical", "high"):
            exp_after += amount
        if sev != r["severity"]:
            movers.append({
                "work_id": r["work_id"], "work_name": r["work_name"], "district": r["district"],
                "from": r["severity"], "to": sev, "old_score": r["risk_score"], "new_score": score,
                "delta": round(score - r["risk_score"], 1),
            })
    movers.sort(key=lambda m: -abs(m["delta"]))
    changed = sum(1 for m in movers)
    # workload estimate: officer-days needed to clear critical + high within SLA
    return {
        "policy": policy, "before": before, "after": after, "matrix": matrix,
        "changed": changed, "movers": movers[:12], "total": len(results),
        "exposure_before": exp_before, "exposure_after": exp_after,
    }


def publish(conn, user, data):
    if user.get("role") != "ministry":
        raise PermissionError("Only ministry users can publish a risk policy")
    policy = _clean_policy(data)
    note = str(data.get("note") or "").strip()[:200] or "Policy update"
    results = _rescore(conn, policy)
    for r, reasons, score, sev in results:
        created = _parse(r["created_at"]) or now_dt()
        due = created + timedelta(days=policy["sla_days"][sev])
        conn.execute(
            "UPDATE alerts SET risk_score = ?, severity = ?, reason_codes = ?, due_at = ?, updated_at = ? WHERE id = ?",
            (score, sev, json.dumps(reasons), due.isoformat(), now_iso(), r["id"]),
        )
    conn.execute(
        "INSERT INTO policy_versions (username, note, policy, created_at) VALUES (?,?,?,?)",
        (user["sub"], note, json.dumps(policy), now_iso()),
    )
    for r in conn.execute("SELECT username FROM users").fetchall():
        if r["username"] != user["sub"]:
            notify(conn, r["username"], "policy", "Risk policy updated by the ministry", note)
    conn.commit()
    db.log_audit(conn, user["sub"], "policy.publish", "risk-policy", note)
    return policy_state(conn)


# ---------------------------------------------------------------------------
# Deterministic demo activity so the workflow screens are not empty on day one
# ---------------------------------------------------------------------------

DEMO_COMMENTS = [
    ("state", "Requested the MB (measurement book) and bill copies from the agency. @district please confirm site status."),
    ("district", "@je.pune visited on Friday - boundary wall done, flooring pending. Photos uploaded to the ePMS."),
    ("je.pune", "Contractor says the last instalment was an advance for material. Asked for the stock register."),
    ("analyst", "Same agency has two near-identical works this FY - keeping this on the watchlist."),
]


def seed_activity(conn):
    rng = random.Random(26102)
    now = now_iso()
    alerts = conn.execute(
        """SELECT a.id, a.work_id, a.severity, w.state, w.district, w.work_name
           FROM alerts a JOIN works w ON w.work_id = a.work_id ORDER BY a.risk_score DESC"""
    ).fetchall()
    for i, a in enumerate(alerts):
        if a["district"] == "Pune":
            owner = rng.choice(["district", "je.pune"])
        elif a["state"] == "Maharashtra":
            owner = rng.choice(["state", "auditor"])
        else:
            owner = rng.choice(["analyst", "ministry"])
        roll = rng.random()
        if i < 4:  # keep a few top critical cases unassigned to surface in "needs attention"
            continue
        if roll < 0.30:
            status, assignee = "in_review", owner
        elif roll < 0.40:
            status, assignee = "actioned", owner
        elif roll < 0.47:
            status, assignee = "dismissed", owner
        else:
            continue
        conn.execute("UPDATE alerts SET status = ?, assignee = ? WHERE id = ?", (status, assignee, a["id"]))
        conn.execute(
            "INSERT INTO alert_actions (alert_id, username, action, note, created_at) VALUES (?,?,?,?,?)",
            (a["id"], owner, "assign", "Assigned during triage", now),
        )
    pune = [a for a in alerts if a["district"] == "Pune"][:3]
    maha = [a for a in alerts if a["state"] == "Maharashtra"][:3]
    for target in (pune + maha)[:4]:
        for username, body in DEMO_COMMENTS[: rng.randint(2, 4)]:
            conn.execute(
                "INSERT INTO comments (work_id, username, body, created_at) VALUES (?,?,?,?)",
                (target["work_id"], username, body, now),
            )
    for username, pool in (("ministry", alerts), ("state", maha), ("district", pune)):
        for a in pool[:3]:
            conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?,?)", (username, a["work_id"], now))
    conn.executemany(
        "INSERT INTO saved_views (username, name, filters, shared, created_at) VALUES (?,?,?,?,?)",
        [
            ("ministry", "Critical & unassigned", json.dumps({"severity": "critical", "assignee": "none"}), 1, now),
            ("ministry", "SLA breached", json.dumps({"sla": "breached"}), 1, now),
            ("ministry", "Money ahead of progress", json.dumps({"code": "PAYMENT_WITHOUT_PROGRESS"}), 1, now),
            ("ministry", "Possible duplicates", json.dumps({"code": "DUPLICATE_WORK"}), 1, now),
        ],
    )
    first = alerts[0] if alerts else None
    for username in ("ministry", "state", "district"):
        notify(conn, username, "digest", "Morning digest: new critical risk signals",
               "Detection run finished - review the unassigned critical cases first.")
        if first:
            notify(conn, username, "sla", "SLA breach on a critical case", first["work_name"], first["work_id"])
    notify(conn, "district", "mention", "S. Kulkarni mentioned you",
           "Please confirm site status for the flagged work.", pune[0]["work_id"] if pune else None)
    conn.commit()
