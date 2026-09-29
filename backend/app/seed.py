"""Seed demo users and a clearly labelled prototype dataset.

No real MPLADS export was available when this project was built, so the CSV written
here is synthetic and is marked as such everywhere it appears. It is pushed through
the same ingestion and risk pipeline as a real upload - nothing is hardcoded.
"""
from __future__ import annotations
import csv, io, random
from datetime import date, timedelta
from pathlib import Path
from sqlalchemy import select
from . import risk, services
from .db import SessionLocal, init_db
from .ingestion import run_ingestion
from .models import Dataset, FieldMapping, User, Work
from .security import hash_password

DEFAULT_PASSWORD = "Drishti@2026"
PROTOTYPE_LABEL = "PROTOTYPE (synthetic) - not a government export"
ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "prototype_mplads_works.csv"
HEADER = ["Work ID", "Work Description", "State", "District", "Constituency", "Work Category",
          "Implementing Agency", "Sanctioned Amount", "Expenditure", "Physical Progress (%)",
          "Date of Sanction", "Expected Completion Date", "Actual Completion Date",
          "Work Status"]
DEMO_USERS = [
    ("admin@drishti.local", "Asha Menon", "ADMIN", None, None),
    ("ministry@drishti.local", "R. Venkatesan", "MINISTRY", None, None),
    ("state@drishti.local", "Sunita Deshmukh", "STATE", "Maharashtra", None),
    ("district@drishti.local", "Imran Qureshi", "DISTRICT", "Maharashtra", "Pune"),
    ("reviewer@drishti.local", "Kavya Iyer", "REVIEWER", "Maharashtra", "Pune"),
    ("auditor@drishti.local", "P. Lakshmanan", "AUDITOR", None, None),
]
GEO = [("Maharashtra", "Pune", "Pune"), ("Maharashtra", "Nashik", "Dindori"),
       ("Karnataka", "Belagavi", "Belgaum"), ("Tamil Nadu", "Madurai", "Madurai"),
       ("Uttar Pradesh", "Varanasi", "Varanasi"), ("Bihar", "Gaya", "Gaya")]
CATEGORIES = [
    ("Community infrastructure", 1_500_000, 6_000_000,
     ["Construction of community hall at {place}", "Extension of panchayat bhavan at {place}"]),
    ("Roads and connectivity", 2_000_000, 9_000_000,
     ["Concrete road from {place} to main road", "Repair of approach road at {place}"]),
    ("Drinking water", 800_000, 4_000_000,
     ["Borewell with pump house at {place}", "Overhead water tank at {place}"]),
    ("Education", 1_200_000, 5_500_000,
     ["Additional classrooms at school in {place}", "Library block at school in {place}"]),
    ("Health", 1_800_000, 7_000_000,
     ["Sub-centre building at {place}", "Ambulance shelter at {place}"]),
    ("Public amenities", 500_000, 2_500_000,
     ["Solar street lights at {place}", "Bus shelter at {place}"]),
]
AGENCIES = ["Zilla Parishad Works Division", "Public Works Department", "Municipal Corporation",
            "Rural Development Agency", "Panchayat Samiti"]
PLACES = ["Wadgaon Sheri", "Kothrud", "Ambegaon", "Sinnar", "Khed", "Hirekop", "Melur",
          "Ramnagar", "Bodh Gaya", "Chunar", "Mundhwa", "Baner"]
STATUSES = ["In progress", "Completed", "Sanctioned", "Stalled"]


def build_prototype_csv(seed: int = 20260913, rows: int = 180) -> bytes:
    """Generate a synthetic dataset with a few deliberately interesting records."""
    rng = random.Random(seed)
    today = date.today()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADER)
    # Demo scenario: high cost, low progress, near-duplicate sibling.
    writer.writerow(["MPL-10427", "Construction of community hall at Wadgaon Sheri",
                     "Maharashtra", "Pune", "Pune", "Community infrastructure",
                     "Zilla Parishad Works Division", 9_850_000, 9_100_000, 22,
                     (today - timedelta(days=690)).isoformat(),
                     (today - timedelta(days=240)).isoformat(), "", "In progress"])
    writer.writerow(["MPL-10904", "Construction of community hall at Wadgaon Sheri village",
                     "Maharashtra", "Pune", "Pune", "Community infrastructure",
                     "Panchayat Samiti", 4_200_000, 1_050_000, 35,
                     (today - timedelta(days=420)).isoformat(),
                     (today + timedelta(days=60)).isoformat(), "", "In progress"])
    for index in range(rows):
        state, district, constituency = rng.choice(GEO)
        name, low, high, templates = rng.choice(CATEGORIES)
        amount = round(rng.uniform(low, high), -3)
        progress = rng.choice([0, 5, 15, 30, 45, 60, 75, 90, 100])
        spent = round(amount * min(1.05, max(0.0, progress / 100 + rng.uniform(-0.15, 0.2))), -3)
        sanctioned_on = today - timedelta(days=rng.randint(60, 900))
        expected = sanctioned_on + timedelta(days=rng.randint(180, 540))
        completed = expected + timedelta(days=rng.randint(-40, 90)) if progress == 100 else ""
        writer.writerow([
            f"MPL-{11000 + index}",
            rng.choice(templates).format(place=rng.choice(PLACES)), state, district,
            constituency, name, rng.choice(AGENCIES), amount, spent, progress,
            sanctioned_on.isoformat(), expected.isoformat(),
            completed.isoformat() if completed else "",
            "Completed" if progress == 100 else rng.choice(STATUSES)])
    # A deliberately malformed row so the rejection report is never empty.
    writer.writerow(["", "Row with no identifier", "Maharashtra", "Pune", "Pune",
                     "Public amenities", "Panchayat Samiti", "not-a-number", "", "",
                     "31-13-2024", "", "", "Sanctioned"])
    return buffer.getvalue().encode()


def seed() -> None:
    init_db()
    session = SessionLocal()
    try:
        services.sync_rules(session)
        for email, full_name, role, state, district in DEMO_USERS:
            if session.scalar(select(User).where(User.email == email)) is None:
                session.add(User(email=email, full_name=full_name, role=role,
                                 password_hash=hash_password(DEFAULT_PASSWORD), state=state,
                                 district=district))
        session.commit()
        admin = session.scalar(select(User).where(User.role == "ADMIN"))
        if session.scalar(select(Work)) is not None:
            print("Works already exist; skipping prototype dataset.")
            return
        content = build_prototype_csv()
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        CSV_PATH.write_bytes(content)
        result = run_ingestion(content, CSV_PATH.name)
        report = result.report()
        dataset = Dataset(filename=CSV_PATH.name, source_label=PROTOTYPE_LABEL,
                          status="PROCESSING", is_prototype=True, size_bytes=len(content),
                          columns=report["columns"],
                          records_received=report["records_received"],
                          records_accepted=report["records_accepted"],
                          records_rejected=report["records_rejected"],
                          warnings=report["warnings"],
                          rejected_records=report["rejected_records"],
                          column_profiles=report["column_profiles"],
                          field_availability=report["field_availability"],
                          uploaded_by_id=admin.id if admin else None)
        session.add(dataset)
        session.commit()
        for field_name, spec in report["mapping"].items():
            session.add(FieldMapping(dataset_id=dataset.id, canonical_field=field_name,
                                     source_column=spec["source_column"], status=spec["status"],
                                     note=spec["note"]))
        for row in result.rows:
            session.add(Work(
                work_id=row["work_id"], dataset_id=dataset.id, description=row.get("description"),
                state=row.get("state"), district=row.get("district"),
                constituency=row.get("constituency"), category=row.get("category"),
                agency=row.get("agency"),
                sanction_amount=risk.parse_number(row.get("sanction_amount")),
                expenditure=risk.parse_number(row.get("expenditure")),
                progress_percent=risk.parse_number(row.get("progress_percent")),
                sanction_date=risk.parse_date(row.get("sanction_date")),
                expected_completion=risk.parse_date(row.get("expected_completion")),
                actual_completion=risk.parse_date(row.get("actual_completion")),
                status=row.get("status"), source_row=row.get("raw")))
        session.commit()
        analysis = services.analyse_dataset(session, admin)
        dataset.status = "COMPLETED"
        session.commit()
        print(f"Seeded {analysis['works_analysed']} works from {PROTOTYPE_LABEL}")
        print(f"Dataset quality {analysis['dataset_quality']['score']} / 100")
        print(f"Demo accounts use the password {DEFAULT_PASSWORD}")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
