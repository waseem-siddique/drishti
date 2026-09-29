"""Upload -> validate -> detect schema -> map fields -> normalise -> report.

Bad records are never silently discarded: every rejection is returned with its
source row number and reason.
"""
from __future__ import annotations
import csv, io, json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
from . import risk

JOB_STATUSES = ("UPLOADED", "VALIDATING", "PROCESSING", "COMPLETED", "FAILED")
ALLOWED_SUFFIXES = (".csv", ".xlsx", ".xls", ".json")
SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "work_id": ("work id", "workid", "work code", "id", "reference", "work reference"),
    "description": ("work description", "description", "work name", "name of work", "particulars"),
    "state": ("state", "state name", "state/ut"),
    "district": ("district", "district name"),
    "constituency": ("constituency", "parliamentary constituency", "mp constituency"),
    "category": ("work category", "category", "sector", "work type"),
    "agency": ("implementing agency", "agency", "executing agency"),
    "sanction_amount": ("sanctioned amount", "sanction amount", "cost", "estimated cost",
                        "amount sanctioned"),
    "expenditure": ("expenditure", "amount spent", "expenditure incurred", "utilised amount"),
    "progress_percent": ("physical progress (%)", "physical progress", "progress",
                         "progress percent"),
    "sanction_date": ("date of sanction", "sanction date", "sanctioned on"),
    "expected_completion": ("expected completion date", "expected completion", "target date",
                            "scheduled completion"),
    "actual_completion": ("actual completion date", "completion date", "date of completion"),
    "status": ("work status", "status", "current status"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "long", "lon"),
}


class IngestionError(Exception):
    pass


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def propose_mapping(columns: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Map source columns onto canonical fields and record what is unavailable."""
    normalised = {_norm(column): column for column in columns}
    mapping: Dict[str, Dict[str, Any]] = {}
    for canonical in risk.CANONICAL_FIELDS:
        source = None
        for candidate in SYNONYMS.get(canonical, ()):
            if candidate in normalised:
                source = normalised[candidate]
                break
        if source is None:
            for key, original in normalised.items():
                if canonical.replace("_", " ") in key:
                    source = original
                    break
        mapping[canonical] = {
            "source_column": source,
            "status": "AVAILABLE" if source else "UNAVAILABLE",
            "note": None if source else f"{risk.NO_DATA}: no source column matched.",
        }
    return mapping


def profile_columns(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> List[Dict[str, Any]]:
    profiles = []
    for column in columns:
        values = [row.get(column) for row in rows]
        present = [value for value in values if value not in (None, "")]
        numeric = [risk.parse_number(value) for value in present]
        profiles.append({
            "column": column, "records": len(values), "populated": len(present),
            "missing_pct": round(100 * (1 - len(present) / len(values)), 2) if values else 100.0,
            "distinct": len({str(value) for value in present}),
            "numeric_share": round(100 * sum(1 for item in numeric if item is not None)
                                   / len(present), 2) if present else 0.0,
            "sample": [str(value)[:60] for value in present[:3]],
        })
    return profiles


@dataclass
class RejectedRecord:
    source_row: int
    reason: str
    payload: Dict[str, Any]


@dataclass
class IngestionResult:
    filename: str
    columns: List[str]
    mapping: Dict[str, Dict[str, Any]]
    rows: List[Dict[str, Any]]
    rejected: List[RejectedRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    column_profiles: List[Dict[str, Any]] = field(default_factory=list)

    def report(self) -> Dict[str, Any]:
        return {
            "filename": self.filename, "columns": self.columns,
            "records_received": len(self.rows) + len(self.rejected),
            "records_accepted": len(self.rows), "records_rejected": len(self.rejected),
            "warnings": self.warnings,
            "rejected_records": [item.__dict__ for item in self.rejected],
            "mapping": self.mapping, "column_profiles": self.column_profiles,
            "field_availability": {key: value["status"] for key, value in self.mapping.items()},
        }


def validate_upload(filename: str, content: bytes, max_mb: int = 64) -> None:
    lowered = (filename or "").lower()
    if not lowered.endswith(ALLOWED_SUFFIXES):
        raise IngestionError("Upload a CSV, Excel or JSON export. "
                             f"'{filename}' is not a supported file type.")
    if not content:
        raise IngestionError("That file is empty.")
    if len(content) > max_mb * 1024 * 1024:
        raise IngestionError(f"That file is larger than the {max_mb} MB upload limit.")


def read_records(filename: str, content: bytes) -> Tuple[List[Dict[str, Any]], List[str]]:
    lowered = filename.lower()
    if lowered.endswith(".json"):
        payload = json.loads(content.decode("utf-8-sig"))
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            raise IngestionError("The JSON file must contain a list of records.")
        columns: List[str] = []
        for record in records:
            for key in record:
                if key not in columns:
                    columns.append(key)
        return [dict(record) for record in records], columns
    if lowered.endswith((".xlsx", ".xls")):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise IngestionError("Excel support needs openpyxl installed on the server.") from exc
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook[workbook.sheetnames[0]]
        iterator = sheet.iter_rows(values_only=True)
        header = [str(cell).strip() if cell is not None else "" for cell in next(iterator, [])]
        records = [{header[index]: value for index, value in enumerate(row)
                    if index < len(header) and header[index]}
                   for row in iterator if any(cell is not None for cell in row)]
        return records, [name for name in header if name]
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise IngestionError("The CSV file has no header row.")
    columns = [name.strip() for name in reader.fieldnames if name]
    return [dict(row) for row in reader], columns


def normalise_rows(records: Sequence[Dict[str, Any]],
                   mapping: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]],
                                                                List[RejectedRecord]]:
    rows: List[Dict[str, Any]] = []
    rejected: List[RejectedRecord] = []
    seen: Dict[str, int] = {}
    for offset, record in enumerate(records):
        source_row = offset + 2  # header occupies row 1
        canonical: Dict[str, Any] = {}
        for field_name, spec in mapping.items():
            column = spec["source_column"]
            canonical[field_name] = record.get(column) if column else None
        work_id = str(canonical.get("work_id") or "").strip()
        if not work_id:
            rejected.append(RejectedRecord(source_row, "Missing work identifier", dict(record)))
            continue
        if work_id in seen:
            rejected.append(RejectedRecord(
                source_row, f"Duplicate work identifier, first seen on row {seen[work_id]}",
                dict(record)))
            continue
        seen[work_id] = source_row
        canonical["work_id"] = work_id
        canonical["source_row"] = source_row
        canonical["raw"] = {key: (str(value) if value is not None else None)
                            for key, value in record.items()}
        rows.append(canonical)
    return rows, rejected


def run_ingestion(content: bytes, filename: str, max_mb: int = 64) -> IngestionResult:
    validate_upload(filename, content, max_mb)
    records, columns = read_records(filename, content)
    if not records:
        raise IngestionError("No data rows were found in that file.")
    mapping = propose_mapping(columns)
    rows, rejected = normalise_rows(records, mapping)
    warnings = [f"{field_name}: {spec['note']}" for field_name, spec in mapping.items()
                if spec["status"] == "UNAVAILABLE"]
    if rejected:
        warnings.append(f"{len(rejected)} record(s) were rejected and are listed in the report.")
    return IngestionResult(filename, columns, mapping, rows, rejected, warnings,
                           profile_columns(records, columns))
