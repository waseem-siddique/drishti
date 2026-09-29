"""DRISHTI API + static file server.

Runs on the Python standard library only:
    python3 backend/app.py            # http://127.0.0.1:8000
    python3 backend/app.py --port 9000 --reseed
"""

import argparse
import json
import mimetypes
mimetypes.add_type("application/manifest+json", ".webmanifest")
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import auth  # noqa: E402
import db  # noqa: E402
import detection  # noqa: E402
import seed as seeder  # noqa: E402
import workflow  # noqa: E402

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_to_dict(row):
    return {k: row[k] for k in row.keys()}


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def fetch_alerts(conn, user, params):
    where, args = [], []
    scope_sql, scope_args = auth.scope_filter(user)
    where.append(scope_sql)
    args.extend(scope_args)

    def one(name):
        value = params.get(name, [None])[0]
        return value if value not in (None, "", "all") else None

    if severity := one("severity"):
        where.append("a.severity = ?")
        args.append(severity)
    if status := one("status"):
        where.append("a.status = ?")
        args.append(status)
    if state := one("state"):
        where.append("w.state = ?")
        args.append(state)
    if district := one("district"):
        where.append("w.district = ?")
        args.append(district)
    if category := one("category"):
        where.append("w.category = ?")
        args.append(category)
    if code := one("code"):
        where.append("a.reason_codes LIKE ?")
        args.append(f'%"{code}"%')
    if assignee := one("assignee"):
        if assignee == "none":
            where.append("a.assignee IS NULL")
        elif assignee == "me":
            where.append("a.assignee = ?")
            args.append(user["sub"])
        else:
            where.append("a.assignee = ?")
            args.append(assignee)
    if sla := one("sla"):
        now = now_iso()
        soon = (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat(timespec="seconds")
        if sla == "breached":
            where.append("a.status IN ('open','in_review') AND a.due_at < ?")
            args.append(now)
        elif sla == "due_soon":
            where.append("a.status IN ('open','in_review') AND a.due_at >= ? AND a.due_at < ?")
            args.extend([now, soon])
    if one("watch") == "1":
        where.append("a.work_id IN (SELECT work_id FROM watchlist WHERE username = ?)")
        args.append(user["sub"])
    if q := one("q"):
        where.append("(w.work_name LIKE ? OR w.work_id LIKE ? OR w.agency LIKE ? OR w.mp_name LIKE ?)")
        args.extend([f"%{q}%"] * 4)

    limit = max(1, min(int(params.get("limit", [25])[0]), 1000))
    page = max(1, int(params.get("page", [1])[0]))
    offset = (page - 1) * limit
    sort = params.get("sort", ["risk"])[0]
    order = {
        "risk": "a.risk_score DESC",
        "amount": "w.sanction_amount DESC",
        "recent": "a.created_at DESC, a.risk_score DESC",
        "progress": "w.physical_progress ASC",
        "due": "a.due_at IS NULL, a.due_at ASC",
    }.get(sort, "a.risk_score DESC")

    clause = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) AS c FROM alerts a JOIN works w ON w.work_id = a.work_id WHERE {clause}",
        args,
    ).fetchone()["c"]
    rows = conn.execute(
        f"""SELECT a.id, a.work_id, a.risk_score, a.severity, a.status, a.confidence,
                   a.reason_codes, a.created_at, a.due_at, a.assignee,
                   w.work_name, w.category, w.state, w.district, w.agency, w.mp_name,
                   w.sanction_amount, w.expenditure, w.physical_progress, w.status AS work_status
            FROM alerts a JOIN works w ON w.work_id = a.work_id
            WHERE {clause} ORDER BY {order} LIMIT ? OFFSET ?""",
        args + [limit, offset],
    ).fetchall()

    items = []
    names = workflow.user_names(conn)
    watched = set(workflow.watched_ids(conn, user))
    for r in rows:
        item = row_to_dict(r)
        reasons = json.loads(item.pop("reason_codes"))
        item["reasons"] = reasons[:3]
        item["reason_count"] = len(reasons)
        item["assignee_name"] = names.get(item["assignee"]) if item["assignee"] else None
        item["sla"], item["sla_hours"] = workflow.sla_state(item["due_at"], item["status"])
        item["watching"] = item["work_id"] in watched
        items.append(item)
    return {"items": items, "total": total, "page": page, "limit": limit}


def build_summary(conn, user):
    scope_sql, scope_args = auth.scope_filter(user)
    base = f"FROM works w WHERE {scope_sql}"

    totals = conn.execute(
        f"""SELECT COUNT(*) AS works,
                   COALESCE(SUM(w.sanction_amount),0) AS sanctioned,
                   COALESCE(SUM(w.expenditure),0) AS spent,
                   COALESCE(AVG(w.physical_progress),0) AS avg_progress,
                   COALESCE(AVG(w.completeness),0) AS avg_completeness
            {base}""",
        scope_args,
    ).fetchone()

    alert_base = f"FROM alerts a JOIN works w ON w.work_id = a.work_id WHERE {scope_sql}"
    severity_rows = conn.execute(
        f"SELECT a.severity, COUNT(*) AS c {alert_base} GROUP BY a.severity", scope_args
    ).fetchall()
    severity = {r["severity"]: r["c"] for r in severity_rows}

    status_rows = conn.execute(
        f"SELECT a.status, COUNT(*) AS c {alert_base} GROUP BY a.status", scope_args
    ).fetchall()

    amount_at_risk = conn.execute(
        f"SELECT COALESCE(SUM(w.sanction_amount),0) AS v {alert_base} AND a.severity IN ('critical','high')",
        scope_args,
    ).fetchone()["v"]

    districts = conn.execute(
        f"""SELECT w.state, w.district, COUNT(a.id) AS alerts,
                   COALESCE(AVG(a.risk_score),0) AS avg_score,
                   COALESCE(SUM(w.sanction_amount),0) AS exposure
            {alert_base} GROUP BY w.state, w.district
            ORDER BY avg_score DESC, alerts DESC LIMIT 12""",
        scope_args,
    ).fetchall()

    categories = conn.execute(
        f"""SELECT w.category, COUNT(a.id) AS alerts, COALESCE(AVG(a.risk_score),0) AS avg_score
            {alert_base} GROUP BY w.category ORDER BY alerts DESC""",
        scope_args,
    ).fetchall()

    reason_counts = {}
    for r in conn.execute(f"SELECT a.reason_codes {alert_base}", scope_args).fetchall():
        for reason in json.loads(r["reason_codes"]):
            reason_counts[reason["code"]] = reason_counts.get(reason["code"], 0) + 1

    trend = conn.execute(
        f"""SELECT substr(w.sanction_date,1,7) AS month,
                   COUNT(*) AS works,
                   COALESCE(SUM(w.expenditure),0) AS spent
            {base} AND w.sanction_date >= '2025-09' GROUP BY month ORDER BY month""",
        scope_args,
    ).fetchall()

    quality = conn.execute(
        f"""SELECT
              SUM(CASE WHEN w.completeness < 0.6 THEN 1 ELSE 0 END) AS poor,
              SUM(CASE WHEN w.completeness >= 0.6 AND w.completeness < 0.85 THEN 1 ELSE 0 END) AS fair,
              SUM(CASE WHEN w.completeness >= 0.85 THEN 1 ELSE 0 END) AS good,
              SUM(CASE WHEN w.expected_completion < '2026-09-01' AND w.physical_progress < 99.5 THEN 1 ELSE 0 END) AS overdue
            {base}""",
        scope_args,
    ).fetchone()

    total_alerts = sum(severity.values())
    feedback = conn.execute("SELECT COALESCE(AVG(useful),0) AS v, COUNT(*) AS c FROM feedback").fetchone()

    return {
        "kpis": {
            "works": totals["works"],
            "sanctioned": totals["sanctioned"],
            "spent": totals["spent"],
            "utilisation": round((totals["spent"] / totals["sanctioned"] * 100) if totals["sanctioned"] else 0, 1),
            "avg_progress": round(totals["avg_progress"], 1),
            "alerts": total_alerts,
            "critical": severity.get("critical", 0),
            "high": severity.get("high", 0),
            "amount_at_risk": amount_at_risk,
            "coverage": 100.0,
            "avg_completeness": round(totals["avg_completeness"] * 100, 1),
            "feedback_useful_pct": round(feedback["v"] * 100, 1),
            "feedback_count": feedback["c"],
        },
        "severity": [
            {"key": k, "value": severity.get(k, 0)} for k in ["critical", "high", "medium", "low"]
        ],
        "status": [row_to_dict(r) for r in status_rows],
        "districts": [row_to_dict(r) for r in districts],
        "categories": [row_to_dict(r) for r in categories],
        "reasons": sorted(
            [{"code": k, "label": detection.RULES.get(k, k), "count": v} for k, v in reason_counts.items()],
            key=lambda x: -x["count"],
        ),
        "trend": [row_to_dict(r) for r in trend],
        "quality": row_to_dict(quality),
        "sla": workflow.sla_summary(conn, user),
    }


def build_case(conn, user, work_id):
    scope_sql, scope_args = auth.scope_filter(user)
    work = conn.execute(
        f"SELECT w.* FROM works w WHERE w.work_id = ? AND {scope_sql}", [work_id] + scope_args
    ).fetchone()
    if not work:
        raise ApiError(404, "Work not found or outside your jurisdiction")
    work = row_to_dict(work)

    alert = conn.execute("SELECT * FROM alerts WHERE work_id = ?", (work_id,)).fetchone()
    alert_data = None
    if alert:
        alert_data = row_to_dict(alert)
        alert_data["reason_codes"] = json.loads(alert_data["reason_codes"])
        alert_data["evidence"] = json.loads(alert_data["evidence"])
        alert_data["actions"] = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM alert_actions WHERE alert_id = ? ORDER BY id DESC", (alert["id"],)
            ).fetchall()
        ]
        alert_data["feedback"] = [
            row_to_dict(r)
            for r in conn.execute(
                "SELECT * FROM feedback WHERE alert_id = ? ORDER BY id DESC", (alert["id"],)
            ).fetchall()
        ]

    payments = [
        row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM payments WHERE work_id = ? ORDER BY pay_date", (work_id,)
        ).fetchall()
    ]
    progress = [
        row_to_dict(r)
        for r in conn.execute(
            "SELECT * FROM progress_updates WHERE work_id = ? ORDER BY update_date", (work_id,)
        ).fetchall()
    ]
    peers = [
        row_to_dict(r)
        for r in conn.execute(
            """SELECT work_id, work_name, sanction_amount, expenditure, physical_progress
               FROM works WHERE category = ? AND district = ? AND work_id != ?
               ORDER BY sanction_amount DESC LIMIT 6""",
            (work["category"], work["district"], work_id),
        ).fetchall()
    ]
    peer_median = conn.execute(
        "SELECT COALESCE(AVG(sanction_amount),0) AS v FROM works WHERE category = ?",
        (work["category"],),
    ).fetchone()["v"]

    if alert_data:
        names = workflow.user_names(conn)
        alert_data["assignee_name"] = names.get(alert_data.get("assignee"))
        alert_data["sla"], alert_data["sla_hours"] = workflow.sla_state(alert_data.get("due_at"), alert_data["status"])
        for act in alert_data["actions"]:
            act["name"] = names.get(act["username"], act["username"])
    return {
        "comments": workflow.comments(conn, work_id),
        "watching": work_id in workflow.watched_ids(conn, user),
        "work": work,
        "alert": alert_data,
        "payments": payments,
        "progress": progress,
        "peers": peers,
        "peer_avg_sanction": peer_median,
    }


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "DRISHTI/2.0"
    protocol_version = "HTTP/1.1"

    # -- plumbing ----------------------------------------------------------
    def log_message(self, fmt, *args):  # quieter console
        if (os.environ.get("DRISHTI_VERBOSE") or os.environ.get("RISKLENS_VERBOSE")):
            super().log_message(fmt, *args)

    def _send(self, status, body: bytes, content_type="application/json; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def json(self, data, status=200):
        self._send(status, json.dumps(data, default=str).encode())

    def error(self, status, message):
        self.json({"error": message}, status)

    def body_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            raise ApiError(400, "Invalid JSON body")

    def current_user(self):
        header = self.headers.get("Authorization", "")
        token = header[7:] if header.lower().startswith("bearer ") else ""
        user = auth.decode_token(token)
        if not user:
            raise ApiError(401, "Session expired - please sign in again")
        return user

    # -- routing -----------------------------------------------------------
    def do_GET(self):
        self.route("GET")

    def do_HEAD(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/"):
                return self.api(method, path, parse_qs(parsed.query))
            return self.static(path)
        except ApiError as exc:
            return self.error(exc.status, exc.message)
        except (sqlite3.Error, ValueError, KeyError, TypeError) as exc:
            return self.error(500, f"Server error: {exc}")

    def api(self, method, path, params):
        conn = db.connect()
        try:
            if path == "/api/health":
                return self.json({"status": "ok", "time": now_iso()})

            if path == "/api/auth/login" and method == "POST":
                data = self.body_json()
                row = conn.execute(
                    "SELECT * FROM users WHERE username = ?", (str(data.get("username", "")).strip(),)
                ).fetchone()
                if not row or not auth.verify_password(str(data.get("password", "")), row["password"]):
                    raise ApiError(401, "Incorrect username or password")
                user = row_to_dict(row)
                db.log_audit(conn, user["username"], "login", "session")
                return self.json(
                    {
                        "token": auth.create_token(user),
                        "user": {
                            "username": user["username"],
                            "name": user["full_name"],
                            "role": user["role"],
                            "state": user["scope_state"],
                            "district": user["scope_district"],
                        },
                    }
                )

            user = self.current_user()

            if path == "/api/me":
                return self.json({"user": user})
            if path == "/api/summary":
                return self.json(build_summary(conn, user))
            if path == "/api/alerts":
                return self.json(fetch_alerts(conn, user, params))
            if path == "/api/filters":
                scope_sql, scope_args = auth.scope_filter(user)
                states = [
                    r["state"]
                    for r in conn.execute(
                        f"SELECT DISTINCT w.state FROM works w WHERE {scope_sql} ORDER BY w.state",
                        scope_args,
                    ).fetchall()
                ]
                districts = [
                    {"state": r["state"], "district": r["district"]}
                    for r in conn.execute(
                        f"SELECT DISTINCT w.state, w.district FROM works w WHERE {scope_sql} ORDER BY w.district",
                        scope_args,
                    ).fetchall()
                ]
                categories = [
                    r["category"]
                    for r in conn.execute(
                        f"SELECT DISTINCT w.category FROM works w WHERE {scope_sql} ORDER BY w.category",
                        scope_args,
                    ).fetchall()
                ]
                return self.json(
                    {
                        "states": states,
                        "districts": districts,
                        "categories": categories,
                        "reason_codes": [
                            {"code": k, "label": v} for k, v in detection.RULES.items()
                        ],
                    }
                )
            if path.startswith("/api/works/") and method == "GET" and path.count("/") == 3:
                return self.json(build_case(conn, user, path.rsplit("/", 1)[-1]))
            if path == "/api/data-quality":
                scope_sql, scope_args = auth.scope_filter(user)
                rows = conn.execute(
                    f"""SELECT w.work_id, w.work_name, w.district, w.state, w.completeness,
                               w.sanction_amount, w.physical_progress
                        FROM works w WHERE {scope_sql} AND w.completeness < 0.75
                        ORDER BY w.completeness ASC LIMIT 60""",
                    scope_args,
                ).fetchall()
                return self.json({"items": [row_to_dict(r) for r in rows]})
            if path == "/api/audit":
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT 150"
                ).fetchall()
                return self.json({"items": [row_to_dict(r) for r in rows]})
            if path == "/api/actions":
                rows = conn.execute(
                    """SELECT aa.*, w.work_name, w.work_id FROM alert_actions aa
                       JOIN alerts a ON a.id = aa.alert_id
                       JOIN works w ON w.work_id = a.work_id
                       ORDER BY aa.id DESC LIMIT 100"""
                ).fetchall()
                return self.json({"items": [row_to_dict(r) for r in rows]})

            # ---- case management & collaboration --------------------------------
            if path == "/api/board":
                return self.json(workflow.board(conn, user, params))
            if path == "/api/users":
                return self.json({"items": workflow.assignable_users(conn, user)})
            if path == "/api/watchlist" and method == "GET":
                return self.json({"items": workflow.watchlist(conn, user)})
            if path == "/api/watchlist/toggle" and method == "POST":
                return self.json(workflow.toggle_watch(conn, user, str(self.body_json().get("work_id", ""))))
            if path == "/api/views" and method == "GET":
                return self.json({"items": workflow.saved_views(conn, user)})
            if path == "/api/views" and method == "POST":
                data = self.body_json()
                try:
                    return self.json({"items": workflow.save_view(conn, user, data.get("name"), data.get("filters"), data.get("shared"))})
                except ValueError as exc:
                    raise ApiError(400, str(exc))
            if path.startswith("/api/views/") and path.endswith("/delete") and method == "POST":
                return self.json({"items": workflow.delete_view(conn, user, int(path.split("/")[3]))})
            if path == "/api/notifications" and method == "GET":
                return self.json(workflow.notifications(conn, user))
            if path == "/api/notifications/read" and method == "POST":
                return self.json(workflow.mark_read(conn, user, self.body_json().get("ids")))
            if path == "/api/scorecards":
                try:
                    return self.json(workflow.scorecards(conn, user, params.get("by", ["agency"])[0]))
                except ValueError as exc:
                    raise ApiError(400, str(exc))
            if path == "/api/policy" and method == "GET":
                return self.json(workflow.policy_state(conn))
            if path == "/api/policy/simulate" and method == "POST":
                try:
                    return self.json(workflow.simulate(conn, self.body_json()))
                except ValueError as exc:
                    raise ApiError(400, str(exc))
            if path == "/api/policy/publish" and method == "POST":
                try:
                    return self.json(workflow.publish(conn, user, self.body_json()))
                except PermissionError as exc:
                    raise ApiError(403, str(exc))
                except ValueError as exc:
                    raise ApiError(400, str(exc))
            if path.startswith("/api/works/") and path.endswith("/comments") and method == "POST":
                work_id = path.split("/")[3]
                build_case(conn, user, work_id)  # enforces jurisdiction
                try:
                    return self.json({"items": workflow.add_comment(conn, user, work_id, self.body_json().get("body"))})
                except ValueError as exc:
                    raise ApiError(400, str(exc))
            if path == "/api/alerts/bulk" and method == "POST":
                data = self.body_json()
                ids = [int(i) for i in (data.get("ids") or [])][:200]
                done = 0
                for alert_id in ids:
                    if "assignee" in data:
                        res = workflow.assign(conn, user, alert_id, data.get("assignee") or None)
                    else:
                        res = workflow.set_status(conn, user, alert_id, str(data.get("status", "")), "Bulk update")
                    done += 1 if res else 0
                return self.json({"ok": True, "updated": done})

            if method == "POST" and path.startswith("/api/alerts/") and path.rsplit("/", 1)[-1] in ("assign", "status"):
                parts = path.strip("/").split("/")
                data = self.body_json()
                try:
                    if parts[3] == "assign":
                        res = workflow.assign(conn, user, int(parts[2]), data.get("assignee") or None)
                    else:
                        res = workflow.set_status(conn, user, int(parts[2]), str(data.get("status", "")), str(data.get("note", ""))[:300])
                except ValueError as exc:
                    raise ApiError(400, str(exc))
                if not res:
                    raise ApiError(404, "Alert not found or outside your jurisdiction")
                return self.json(res)

            if method == "POST" and path.startswith("/api/alerts/"):
                parts = path.strip("/").split("/")
                alert_id = int(parts[2])
                verb = parts[3] if len(parts) > 3 else ""
                data = self.body_json()
                alert = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
                if not alert:
                    raise ApiError(404, "Alert not found")

                if verb == "action":
                    action = str(data.get("action", "")).strip()
                    if action not in {"acknowledge", "assign_inspection", "seek_clarification", "escalate", "dismiss"}:
                        raise ApiError(400, "Unsupported action")
                    new_status = {
                        "acknowledge": "in_review",
                        "assign_inspection": "in_review",
                        "seek_clarification": "in_review",
                        "escalate": "actioned",
                        "dismiss": "dismissed",
                    }[action]
                    conn.execute(
                        "INSERT INTO alert_actions (alert_id, username, action, note, created_at) VALUES (?,?,?,?,?)",
                        (alert_id, user["sub"], action, str(data.get("note", ""))[:500], now_iso()),
                    )
                    conn.execute(
                        "UPDATE alerts SET status = ?, updated_at = ? WHERE id = ?",
                        (new_status, now_iso(), alert_id),
                    )
                    conn.commit()
                    db.log_audit(conn, user["sub"], f"alert.{action}", alert["work_id"], data.get("note"))
                    return self.json({"ok": True, "status": new_status})

                if verb == "feedback":
                    useful = 1 if data.get("useful") else 0
                    conn.execute(
                        "INSERT INTO feedback (alert_id, username, useful, created_at) VALUES (?,?,?,?)",
                        (alert_id, user["sub"], useful, now_iso()),
                    )
                    conn.commit()
                    db.log_audit(conn, user["sub"], "alert.feedback", alert["work_id"], f"useful={bool(useful)}")
                    return self.json({"ok": True})

                raise ApiError(404, "Unknown alert operation")

            if path == "/api/detect/run" and method == "POST":
                if user.get("role") not in ("ministry", "state"):
                    raise ApiError(403, "Only ministry or state users can re-run detection")
                created = detection.run_detection(conn)
                db.log_audit(conn, user["sub"], "detection.run", "engine", f"{created} alerts")
                return self.json({"ok": True, "alerts": created})

            raise ApiError(404, "Unknown endpoint")
        finally:
            conn.close()

    # -- static files ------------------------------------------------------
    def static(self, path):
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = os.path.normpath(os.path.join(FRONTEND_DIR, rel))
        if not target.startswith(FRONTEND_DIR):
            return self.error(403, "Forbidden")
        if not os.path.isfile(target):
            target = os.path.join(FRONTEND_DIR, "index.html")  # SPA fallback
        ctype, _ = mimetypes.guess_type(target)
        with open(target, "rb") as fh:
            body = fh.read()
        cache = "public, max-age=3600" if "/assets/" in path else "no-cache"
        self._send(200, body, ctype or "application/octet-stream", {"Cache-Control": cache})


def bootstrap(reseed=False):
    conn = db.connect()
    db.init_schema(conn)
    if reseed or not db.is_seeded(conn):
        works, payments = seeder.seed(conn)
        alerts = detection.run_detection(conn)
        workflow.seed_activity(conn)
        db.log_audit(conn, "system", "bootstrap", "database", f"{works} works, {alerts} alerts")
        print(f"  seeded {works} works, {payments} payments -> {alerts} alerts")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="DRISHTI server")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--reseed", action="store_true", help="rebuild the demo dataset")
    args = parser.parse_args()

    bootstrap(args.reseed)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"\n  DRISHTI running at http://{args.host}:{args.port}")
    print("  demo logins: ministry / state / district   (password: drishti)\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
