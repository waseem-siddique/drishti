"""Engine tests: parsing, gating, detectors, composition, confidence, priority, quality."""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app import ingestion, risk  # noqa: E402

TODAY = date(2026, 6, 1)


def make_row(**overrides):
    row = {"work_id": "MPL-1", "description": "Construction of community hall at Baner",
           "state": "Maharashtra", "district": "Pune", "category": "Community infrastructure",
           "agency": "Zilla Parishad", "sanction_amount": 2_000_000, "expenditure": 1_000_000,
           "progress_percent": 50, "sanction_date": "2025-01-10",
           "expected_completion": "2025-12-01", "actual_completion": "", "status": "In progress"}
    row.update(overrides)
    return row


def test_number_and_date_parsing():
    assert risk.parse_number("Rs. 12,50,000") == 1250000.0
    assert risk.parse_number("not-a-number") is None
    assert risk.parse_date("31-13-2024") is None
    assert risk.parse_date("10/03/2025") == date(2025, 3, 10)


def test_rule_is_gated_when_required_field_missing():
    work = risk.Work.from_row(make_row(progress_percent=""))
    verdict = risk.evaluate_gating(work, risk.RULES_BY_ID["EXE-PROG-001"])
    assert verdict.evaluated is False
    assert "progress_percent" in verdict.missing_fields


def test_progress_gap_signal_fires_and_is_explainable():
    rows = [make_row(work_id=f"MPL-{index}") for index in range(10)]
    rows.append(make_row(work_id="MPL-X", expenditure=1_900_000, progress_percent=10))
    analysis = risk.analyse_population(rows, as_of=TODAY)
    target = next(item for item in analysis.results if item.work.work_id == "MPL-X")
    signal = next(item for item in target.signals if item.rule_id == "EXE-PROG-001")
    assert signal.statement and signal.evidence and signal.recommended_actions
    assert signal.false_positive_notes


def test_duplicate_detector_finds_near_duplicate():
    rows = [make_row(work_id="MPL-A"),
            make_row(work_id="MPL-B",
                     description="Construction of community hall at Baner village")]
    analysis = risk.analyse_population(rows, as_of=TODAY)
    assert [item for item in analysis.results
            if any(signal.rule_id == "DUP-SIM-001" for signal in item.signals)]


def test_composition_is_capped_and_banded():
    composition = risk.compose([])
    assert composition["risk_score"] == 0.0
    assert composition["risk_band"] == "LOW"
    assert risk.band_for(85) == "HIGH"
    assert risk.band_for(50) == "MEDIUM"


def test_missing_data_lowers_confidence_not_risk():
    complete = risk.analyse_population([make_row()], as_of=TODAY).results[0]
    sparse = risk.analyse_population([make_row(agency="", expenditure="")],
                                     as_of=TODAY).results[0]
    assert sparse.confidence["confidence_score"] < complete.confidence["confidence_score"]
    assert sparse.quality["score"] < complete.quality["score"]


def test_priority_index_is_separate_from_risk():
    result = risk.analyse_population([make_row()], as_of=TODAY).results[0]
    assert result.priority["priority"] in ("P1", "P2", "P3")
    assert set(result.priority["priority_components"]) == {
        "risk", "confidence", "impact", "urgency", "actionability"}


def test_ingestion_rejects_bad_rows_without_dropping_them_silently():
    csv_bytes = (b"Work ID,Work Description,Sanctioned Amount\n"
                 b"MPL-1,Road at Baner,100000\n"
                 b",Row with no id,50000\n"
                 b"MPL-1,Duplicate id,70000\n")
    result = ingestion.run_ingestion(csv_bytes, "sample.csv")
    assert len(result.rows) == 1
    assert len(result.rejected) == 2
    reasons = " ".join(item.reason for item in result.rejected)
    assert "identifier" in reasons and "uplicate" in reasons


def test_unavailable_columns_are_reported_not_invented():
    mapping = ingestion.propose_mapping(["Work ID", "Work Description"])
    assert mapping["latitude"]["status"] == "UNAVAILABLE"


def test_overdue_signal_uses_real_date_arithmetic():
    overdue = make_row(work_id="MPL-LATE",
                       expected_completion=(TODAY - timedelta(days=400)).isoformat())
    result = risk.analyse_population([overdue], as_of=TODAY).results[0]
    assert any(signal.rule_id == "EXE-DELAY-003" for signal in result.signals)
