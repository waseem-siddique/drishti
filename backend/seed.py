"""Deterministic synthetic MPLADS demo dataset.

The generator mimics the record types the scheme produces (sanction,
estimate, payment, progress, completion) and deliberately injects a realistic
mix of risky cases so the detection engine has something to find.
Standard library only.
"""

import csv
import os
import random
from datetime import date, timedelta

from auth import hash_password
from db import DATA_DIR

SEED = 26102
TODAY = date(2026, 9, 1)

STATES = {
    "Maharashtra": ["Pune", "Nagpur", "Nashik", "Thane", "Aurangabad"],
    "Uttar Pradesh": ["Lucknow", "Varanasi", "Kanpur", "Gorakhpur"],
    "Karnataka": ["Bengaluru Urban", "Mysuru", "Belagavi"],
    "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai"],
    "Bihar": ["Patna", "Gaya", "Muzaffarpur"],
    "Rajasthan": ["Jaipur", "Jodhpur", "Udaipur"],
}

CATEGORIES = {
    "Roads and Bridges": (1_500_000, 9_000_000),
    "Drinking Water": (400_000, 3_500_000),
    "Education": (800_000, 6_000_000),
    "Health": (1_000_000, 7_500_000),
    "Sanitation": (300_000, 2_500_000),
    "Community Assets": (500_000, 4_000_000),
    "Electricity and Solar": (600_000, 5_000_000),
    "Sports and Youth": (400_000, 3_000_000),
}

WORK_TEMPLATES = {
    "Roads and Bridges": [
        "Construction of CC road at {loc}",
        "Repair of approach road near {loc}",
        "Construction of culvert at {loc}",
    ],
    "Drinking Water": [
        "Installation of RO water plant at {loc}",
        "Construction of overhead water tank at {loc}",
        "Borewell with submersible pump at {loc}",
    ],
    "Education": [
        "Additional classroom block at Govt School, {loc}",
        "Smart classroom facility at {loc}",
        "Library building at {loc}",
    ],
    "Health": [
        "Ambulance for PHC {loc}",
        "Upgradation of sub-centre at {loc}",
        "Dialysis unit equipment at {loc}",
    ],
    "Sanitation": [
        "Community toilet block at {loc}",
        "Drainage line construction at {loc}",
        "Solid waste collection vehicles for {loc}",
    ],
    "Community Assets": [
        "Community hall at {loc}",
        "Renovation of panchayat bhavan at {loc}",
        "Crematorium shed at {loc}",
    ],
    "Electricity and Solar": [
        "Solar street lights at {loc}",
        "High mast light installation at {loc}",
        "Solar rooftop for school at {loc}",
    ],
    "Sports and Youth": [
        "Open gym equipment at {loc}",
        "Playground development at {loc}",
        "Volleyball court at {loc}",
    ],
}

LOCALITIES = [
    "Ward 4", "Ward 11", "Shivaji Nagar", "Gandhi Chowk", "Bhagat Singh Colony",
    "Rampur village", "Krishna Nagar", "Ambedkar Vasti", "Station Road",
    "Nehru Ward", "Subhash Nagar", "Tilak Road", "Sector 9", "Indira Colony",
    "Patel Nagar", "Sundar Vihar", "Laxmi Nagar", "Vidya Nagar",
]

MPS = [
    ("Anil Deshmukh", "Lok Sabha"), ("Sunita Rao", "Lok Sabha"),
    ("R. Krishnan", "Rajya Sabha"), ("Meera Yadav", "Lok Sabha"),
    ("P. Nagarajan", "Lok Sabha"), ("Farhan Qureshi", "Rajya Sabha"),
    ("Kavita Sharma", "Lok Sabha"), ("J. Baruah", "Lok Sabha"),
    ("Vikram Chauhan", "Rajya Sabha"), ("Latha Menon", "Lok Sabha"),
]

AGENCIES = [
    "PWD Division", "Zilla Parishad", "Municipal Corporation",
    "Rural Engineering Service", "Jal Nigam", "Block Development Office",
]

USERS = [
    ("ministry", "drishti", "Dr. A. Sengupta", "ministry", None, None),
    ("state", "drishti", "S. Kulkarni (Nodal, Maharashtra)", "state", "Maharashtra", None),
    ("district", "drishti", "R. Pawar (DM, Pune)", "district", "Maharashtra", "Pune"),
    ("analyst", "drishti", "K. Verma (MoSPI analyst)", "ministry", None, None),
    ("auditor", "drishti", "N. Iyer (Field auditor)", "state", "Maharashtra", None),
    ("je.pune", "drishti", "A. Joshi (Junior Engineer, Pune)", "district", "Maharashtra", "Pune"),
]


def _fy(d: date) -> str:
    return f"{d.year}-{str(d.year + 1)[2:]}" if d.month >= 4 else f"{d.year - 1}-{str(d.year)[2:]}"


def _round(value: float) -> float:
    return float(round(value, 2))


def generate(rng: random.Random):
    works, payments, progress = [], [], []
    counter = 1

    plan = []
    for state, districts in STATES.items():
        for district in districts:
            plan.extend([(state, district)] * rng.randint(11, 16))

    for state, district in plan:
        category = rng.choice(list(CATEGORIES))
        low, high = CATEGORIES[category]
        locality = rng.choice(LOCALITIES)
        name = rng.choice(WORK_TEMPLATES[category]).format(loc=f"{locality}, {district}")
        mp_name, house = rng.choice(MPS)
        agency = rng.choice(AGENCIES)

        sanction_date = TODAY - timedelta(days=rng.randint(40, 900))
        recommended_date = sanction_date - timedelta(days=rng.randint(20, 120))
        estimate = _round(rng.uniform(low, high))
        sanction = _round(estimate * rng.uniform(0.95, 1.05))
        duration = rng.randint(120, 420)
        expected_completion = sanction_date + timedelta(days=duration)

        profile = rng.random()
        anomaly = None
        if profile < 0.055:
            anomaly = "cost_overrun"
        elif profile < 0.105:
            anomaly = "payment_without_progress"
        elif profile < 0.155:
            anomaly = "stalled"
        elif profile < 0.195:
            anomaly = "burst"
        elif profile < 0.225:
            anomaly = "outlier_cost"

        elapsed = (TODAY - sanction_date).days
        natural_progress = min(100.0, max(0.0, (elapsed / duration) * rng.uniform(75, 115)))
        physical_progress = round(natural_progress, 1)
        expenditure = _round(sanction * (physical_progress / 100.0) * rng.uniform(0.9, 1.05))
        completeness = round(rng.uniform(0.72, 1.0), 2)

        if anomaly == "cost_overrun":
            expenditure = _round(sanction * rng.uniform(1.25, 1.85))
            physical_progress = round(rng.uniform(55, 92), 1)
        elif anomaly == "payment_without_progress":
            expenditure = _round(sanction * rng.uniform(0.62, 0.9))
            physical_progress = round(rng.uniform(2, 20), 1)
        elif anomaly == "stalled":
            physical_progress = round(rng.uniform(15, 55), 1)
            expenditure = _round(sanction * (physical_progress / 100.0))
        elif anomaly == "outlier_cost":
            sanction = _round(high * rng.uniform(2.4, 3.6))
            estimate = _round(sanction * rng.uniform(0.9, 1.0))
            expenditure = _round(sanction * (physical_progress / 100.0))
        if rng.random() < 0.09:
            completeness = round(rng.uniform(0.28, 0.55), 2)

        completed = physical_progress >= 99.5 and anomaly not in ("stalled", "payment_without_progress")
        actual_completion = ""
        if completed:
            physical_progress = 100.0
            actual_completion = (
                expected_completion + timedelta(days=rng.randint(-60, 90))
            ).isoformat()
            status = "Completed"
        elif physical_progress <= 1:
            status = "Sanctioned"
        else:
            status = "In Progress"

        work_id = f"MP{sanction_date.year}{counter:04d}"
        counter += 1

        works.append(
            {
                "work_id": work_id,
                "work_name": name,
                "category": category,
                "mp_name": mp_name,
                "house": house,
                "state": state,
                "district": district,
                "agency": f"{agency}, {district}",
                "recommended_date": recommended_date.isoformat(),
                "sanction_date": sanction_date.isoformat(),
                "sanction_amount": sanction,
                "estimate_amount": estimate,
                "expenditure": expenditure,
                "physical_progress": physical_progress,
                "expected_completion": expected_completion.isoformat(),
                "actual_completion": actual_completion,
                "status": status,
                "beneficiaries": rng.randint(250, 22000),
                "completeness": completeness,
                "fiscal_year": _fy(sanction_date),
            }
        )

        # ---- payment instalments -------------------------------------------
        remaining = expenditure
        if anomaly == "burst":
            first = _round(expenditure * rng.uniform(0.7, 0.95))
            schedule = [first, _round(max(0.0, expenditure - first))]
        else:
            n = rng.randint(2, 4)
            parts = [rng.uniform(0.6, 1.4) for _ in range(n)]
            total = sum(parts)
            schedule = [_round(expenditure * p / total) for p in parts]
        pay_day = sanction_date + timedelta(days=rng.randint(10, 45))
        last_gap = 200 if anomaly == "stalled" else rng.randint(35, 110)
        for idx, amount in enumerate(schedule):
            if amount <= 0:
                continue
            share = sum(schedule[: idx + 1]) / max(expenditure, 1)
            payments.append(
                {
                    "work_id": work_id,
                    "pay_date": pay_day.isoformat(),
                    "amount": amount,
                    "progress_at_payment": round(physical_progress * share, 1),
                    "voucher": f"VCH/{work_id}/{idx + 1}",
                }
            )
            progress.append(
                {
                    "work_id": work_id,
                    "update_date": pay_day.isoformat(),
                    "progress": round(physical_progress * share, 1),
                    "remark": "Progress recorded with instalment",
                }
            )
            pay_day = min(pay_day + timedelta(days=last_gap), TODAY - timedelta(days=1))
        remaining = remaining  # kept for readability of instalment logic

    # ---- injected duplicate / split-work clusters ---------------------------
    duplicates = []
    for src in rng.sample([w for w in works if w["status"] != "Completed"], 9):
        clone = dict(src)
        clone["work_id"] = f"MP{src['sanction_date'][:4]}{counter:04d}"
        counter += 1
        clone["sanction_date"] = (
            date.fromisoformat(src["sanction_date"]) + timedelta(days=rng.randint(20, 90))
        ).isoformat()
        clone["sanction_amount"] = _round(src["sanction_amount"] * rng.uniform(0.96, 1.06))
        clone["estimate_amount"] = _round(clone["sanction_amount"] * 0.98)
        clone["expenditure"] = _round(clone["sanction_amount"] * rng.uniform(0.3, 0.8))
        clone["physical_progress"] = round(rng.uniform(10, 60), 1)
        clone["status"] = "In Progress"
        clone["actual_completion"] = ""
        duplicates.append(clone)
        payments.append(
            {
                "work_id": clone["work_id"],
                "pay_date": clone["sanction_date"],
                "amount": clone["expenditure"],
                "progress_at_payment": clone["physical_progress"],
                "voucher": f"VCH/{clone['work_id']}/1",
            }
        )
        progress.append(
            {
                "work_id": clone["work_id"],
                "update_date": clone["sanction_date"],
                "progress": clone["physical_progress"],
                "remark": "Initial progress report",
            }
        )
    works.extend(duplicates)
    return works, payments, progress


def write_csv(rows, path, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def seed(conn, export_csv=True):
    rng = random.Random(SEED)
    works, payments, progress = generate(rng)

    conn.execute("DELETE FROM feedback")
    conn.execute("DELETE FROM alert_actions")
    conn.execute("DELETE FROM alerts")
    conn.execute("DELETE FROM payments")
    conn.execute("DELETE FROM progress_updates")
    conn.execute("DELETE FROM works")
    conn.execute("DELETE FROM users")
    for table in ("comments", "watchlist", "saved_views", "notifications", "policy_versions"):
        conn.execute(f"DELETE FROM {table}")

    work_fields = list(works[0].keys())
    conn.executemany(
        f"INSERT INTO works ({','.join(work_fields)}) VALUES ({','.join('?' * len(work_fields))})",
        [tuple(w[f] for f in work_fields) for w in works],
    )
    conn.executemany(
        "INSERT INTO payments (work_id, pay_date, amount, progress_at_payment, voucher)"
        " VALUES (?,?,?,?,?)",
        [(p["work_id"], p["pay_date"], p["amount"], p["progress_at_payment"], p["voucher"]) for p in payments],
    )
    conn.executemany(
        "INSERT INTO progress_updates (work_id, update_date, progress, remark) VALUES (?,?,?,?)",
        [(p["work_id"], p["update_date"], p["progress"], p["remark"]) for p in progress],
    )
    conn.executemany(
        "INSERT INTO users (username, password, full_name, role, scope_state, scope_district)"
        " VALUES (?,?,?,?,?,?)",
        [(u[0], hash_password(u[1]), u[2], u[3], u[4], u[5]) for u in USERS],
    )
    conn.commit()

    if export_csv:
        os.makedirs(DATA_DIR, exist_ok=True)
        write_csv(works, os.path.join(DATA_DIR, "works.csv"), work_fields)
        write_csv(
            payments,
            os.path.join(DATA_DIR, "payments.csv"),
            ["work_id", "pay_date", "amount", "progress_at_payment", "voucher"],
        )
        write_csv(
            progress,
            os.path.join(DATA_DIR, "progress_updates.csv"),
            ["work_id", "update_date", "progress", "remark"],
        )
    return len(works), len(payments)
