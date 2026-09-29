"""Deterministic risk engine. No language model participates in scoring.

Pipeline: canonical fields -> data quality -> deterministic rules -> statistical
detectors -> risk composer -> confidence -> verification priority.
"""
from __future__ import annotations
import math, re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

ENGINE_VERSION = "0.4"
COMPOSER_VERSION = "0.4"
CONFIDENCE_VERSION = "0.3"
PRIORITY_VERSION = "0.3"
QUALITY_VERSION = "0.3"
ONTOLOGY_VERSION = "1.0.0"
TRANSPARENCY_NOTE = ("DRISHTI provides risk-based decision support. A risk score does not "
                     "establish fraud or misconduct. Final determination requires authorized "
                     "human verification.")
QUALITY_NOTE = ("Missing data is not treated as normal. Low data quality reduces the confidence "
                "attached to a risk result instead of raising or lowering risk.")
PREDICTIVE_METHODOLOGY = ("Unsupervised linear extrapolation of reported progress. No labelled "
                          "fraud outcomes exist in the dataset, so this is an early warning, "
                          "not a prediction of misconduct.")
NO_DATA = "Not present in current dataset"

CANONICAL_FIELDS = ("work_id", "description", "state", "district", "constituency", "category",
                    "agency", "sanction_amount", "expenditure", "progress_percent",
                    "sanction_date", "expected_completion", "actual_completion", "status",
                    "latitude", "longitude")
MANDATORY_FIELDS = ("work_id", "description", "state", "district", "category", "agency",
                    "sanction_amount", "expenditure", "sanction_date")
NUMERIC_FIELDS = ("sanction_amount", "expenditure", "progress_percent", "latitude", "longitude")
DATE_FIELDS = ("sanction_date", "expected_completion", "actual_completion")
_DATE_PATTERNS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d %b %Y",
                  "%m/%d/%Y", "%Y-%m-%d %H:%M:%S")
_STOPWORDS = {"of", "at", "in", "the", "for", "and", "to", "a", "on", "with", "work", "works",
              "village", "ward", "construction", "providing"}


def parse_date(value: Any) -> Optional[date]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for pattern in _DATE_PATTERNS:
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def parse_number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = re.sub(r"(?i)(rs\.?|inr)", "", re.sub(r"[,\s\u20b9]", "", str(value)))
    if text in ("", "-", "NA", "na", "N/A", "null", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def normalise_description(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (value or "").lower()).strip()


def description_tokens(value: Optional[str]) -> set:
    return {token for token in normalise_description(value).split()
            if len(token) > 2 and token not in _STOPWORDS}


@dataclass
class Work:
    work_id: str
    description: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    constituency: Optional[str] = None
    category: Optional[str] = None
    agency: Optional[str] = None
    sanction_amount: Optional[float] = None
    expenditure: Optional[float] = None
    progress_percent: Optional[float] = None
    sanction_date: Optional[date] = None
    expected_completion: Optional[date] = None
    actual_completion: Optional[date] = None
    status: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Work":
        payload: Dict[str, Any] = {}
        for name in CANONICAL_FIELDS:
            value = row.get(name)
            if name in NUMERIC_FIELDS:
                payload[name] = parse_number(value)
            elif name in DATE_FIELDS:
                payload[name] = parse_date(value)
            else:
                payload[name] = (str(value).strip() or None) if value not in (None, "") else None
        payload["work_id"] = str(row.get("work_id") or "").strip()
        return cls(**payload)

    @property
    def utilisation(self) -> Optional[float]:
        if self.sanction_amount and self.expenditure is not None and self.sanction_amount > 0:
            return self.expenditure / self.sanction_amount
        return None

    def days_overdue(self, as_of: date) -> Optional[int]:
        if self.expected_completion is None or self.actual_completion is not None:
            return None
        return max(0, (as_of - self.expected_completion).days)

    def feature_snapshot(self, as_of: date) -> Dict[str, Any]:
        return {"sanction_amount": self.sanction_amount, "expenditure": self.expenditure,
                "progress_percent": self.progress_percent, "utilisation": self.utilisation,
                "days_overdue": self.days_overdue(as_of), "category": self.category,
                "district": self.district, "state": self.state,
                "sanction_date": self.sanction_date.isoformat() if self.sanction_date else None}


def field_availability(rows: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    return {name: ("AVAILABLE" if any(row.get(name) not in (None, "") for row in rows)
                   else "UNAVAILABLE") for name in CANONICAL_FIELDS}


CATEGORIES = {"FIN": "Financial and cost", "EXE": "Execution and progress",
              "DUP": "Duplication and similarity", "CMP": "Compliance and data integrity",
              "PRD": "Early warning"}
SEVERITY_CEILING = {"LOW": 10.0, "MEDIUM": 20.0, "HIGH": 30.0}


@dataclass(frozen=True)
class RiskRule:
    rule_id: str
    name: str
    category: str
    severity: str
    description: str
    method: str
    required_fields: Tuple[str, ...]
    evidence_fields: Tuple[str, ...]
    recommended_actions: Tuple[str, ...]
    false_positive_notes: str
    params: Dict[str, float]
    weight: float = 1.0
    version: str = "1.0"


RULES: Tuple[RiskRule, ...] = (
    RiskRule("FIN-COST-001", "Sanctioned cost far above comparable works", "FIN", "HIGH",
             "Sanctioned amount is a robust statistical outlier within its peer group.",
             "robust-z (median/MAD) against contextual peer group",
             ("sanction_amount", "category"), ("sanction_amount", "category", "district"),
             ("Compare the estimate with the schedule of rates",
              "Obtain the detailed estimate and approval note"),
             "Larger or specialised works can be legitimate outliers; small peer groups are "
             "statistically weak.", {"trigger_z": 2.5, "saturate_z": 6.0, "min_peers": 8}, 0.7),
    RiskRule("FIN-UTIL-002", "Expenditure exceeds sanctioned amount", "FIN", "HIGH",
             "Reported expenditure is higher than the sanctioned amount.",
             "deterministic ratio threshold", ("sanction_amount", "expenditure"),
             ("sanction_amount", "expenditure"),
             ("Reconcile the expenditure statement against the sanction order",),
             "Revised sanctions are absent from this dataset, so a legitimate revision can look "
             "like an overrun.", {"trigger_ratio": 1.0, "saturate_ratio": 1.4}),
    RiskRule("EXE-PROG-001", "Spending far ahead of reported physical progress", "EXE", "HIGH",
             "Financial utilisation is much higher than reported physical progress.",
             "deterministic gap between utilisation and progress",
             ("sanction_amount", "expenditure", "progress_percent"),
             ("expenditure", "progress_percent"),
             ("Request the latest measurement book entry",
              "Schedule a site verification with photographs"),
             "Progress reporting lags, and material advances create a legitimate gap.",
             {"trigger_gap": 25.0, "saturate_gap": 70.0}),
    RiskRule("EXE-STAG-002", "Funds released with negligible progress", "EXE", "MEDIUM",
             "Money has moved but reported physical progress is near zero.",
             "deterministic threshold on utilisation with low progress",
             ("expenditure", "progress_percent"), ("expenditure", "progress_percent", "status"),
             ("Ask the implementing agency for a current status note",),
             "Mobilisation advances and seasonal stoppages can explain this pattern.",
             {"trigger_ratio": 0.10, "saturate_ratio": 0.50, "progress_ceiling": 10.0}),
    RiskRule("EXE-DELAY-003", "Overdue beyond the expected completion date", "EXE", "MEDIUM",
             "The expected completion date has passed with no recorded completion.",
             "deterministic date arithmetic", ("expected_completion",),
             ("expected_completion", "actual_completion", "status"),
             ("Obtain a revised completion timeline",),
             "Time extensions are not recorded in this dataset.",
             {"trigger_days": 90.0, "saturate_days": 730.0}),
    RiskRule("DUP-SIM-001", "Near-duplicate work in the same area", "DUP", "HIGH",
             "Another work in the same district and category has a similar description.",
             "character n-gram cosine blended with token Jaccard similarity",
             ("description", "district"), ("description", "district", "category"),
             ("Compare both sanction orders and locations",
              "Confirm on site whether two distinct assets exist"),
             "Phased and repeated standard works are often legitimately similar.",
             {"trigger_similarity": 0.82, "saturate_similarity": 0.97}),
    RiskRule("CMP-DATA-001", "Mandatory fields missing from the record", "CMP", "MEDIUM",
             "Fields required for oversight are absent, which limits verification.",
             "deterministic completeness check", (), ("work_id",),
             ("Ask the reporting office to complete the record",),
             "Missing data is a reporting failure, not evidence of misconduct.",
             {"trigger_missing": 1.0, "saturate_missing": 4.0}, 0.8),
    RiskRule("CMP-CHRON-002", "Chronologically impossible dates", "CMP", "MEDIUM",
             "Recorded dates contradict each other.", "deterministic date consistency check",
             ("sanction_date",), ("sanction_date", "expected_completion", "actual_completion"),
             ("Correct the record at source and re-upload",),
             "Data entry errors are the most common cause.", {"per_violation": 0.45}),
    RiskRule("PRD-TRAJ-001", "Reported trajectory will miss the deadline", "PRD", "MEDIUM",
             "Linear extrapolation of progress does not reach completion by the expected date.",
             "unsupervised linear extrapolation",
             ("progress_percent", "sanction_date", "expected_completion"),
             ("progress_percent", "sanction_date", "expected_completion"),
             ("Review the work plan with the implementing agency",), PREDICTIVE_METHODOLOGY,
             {"trigger_shortfall": 15.0, "saturate_shortfall": 60.0}, 0.7),
)
RULES_BY_ID = {rule.rule_id: rule for rule in RULES}


@dataclass
class GateVerdict:
    rule_id: str
    evaluated: bool
    missing_fields: Tuple[str, ...] = ()

    @property
    def reason(self) -> Optional[str]:
        if self.evaluated:
            return None
        return f"Not evaluated: {', '.join(self.missing_fields)} {NO_DATA.lower()}"


def evaluate_gating(work: Work, rule: RiskRule) -> GateVerdict:
    missing = tuple(name for name in rule.required_fields
                    if getattr(work, name, None) in (None, ""))
    return GateVerdict(rule.rule_id, not missing, missing)


MAD_TO_SIGMA = 1.4826


def _quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = (len(ordered) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return ordered[int(position)]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


@dataclass
class PeerStats:
    dimensions: Dict[str, Optional[str]]
    metric: str
    values: List[float]

    @property
    def peer_count(self) -> int:
        return len(self.values)

    @property
    def median(self) -> float:
        return _quantile(self.values, 0.5)

    def robust_z(self, value: float) -> Optional[float]:
        if self.peer_count < 4:
            return None
        mad = _quantile([abs(item - self.median) for item in self.values], 0.5) * MAD_TO_SIGMA
        if mad <= 0:
            spread = _quantile(self.values, 0.75) - _quantile(self.values, 0.25)
            mad = spread / 1.349 if spread > 0 else 0.0
        return (value - self.median) / mad if mad > 0 else None

    def percentile(self, value: float) -> Optional[float]:
        if not self.values:
            return None
        return round(100.0 * sum(1 for item in self.values if item <= value) / self.peer_count, 1)

    def to_dict(self, value: Optional[float] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"dimensions": self.dimensions, "metric": self.metric,
                                   "peer_count": self.peer_count,
                                   "median": round(self.median, 2),
                                   "p25": round(_quantile(self.values, 0.25), 2),
                                   "p75": round(_quantile(self.values, 0.75), 2)}
        if value is not None:
            robust = self.robust_z(value)
            payload.update({"value": value, "percentile": self.percentile(value),
                            "robust_z": round(robust, 2) if robust is not None else None})
        return payload


class PeerIndex:
    """Peer groups are contextual: category in district, then state, then national."""

    LEVELS = (("category", "district"), ("category", "state"), ("category",))

    def __init__(self, works: Sequence[Work], metric: str = "sanction_amount") -> None:
        self.metric = metric
        self.groups: Dict[Tuple, PeerStats] = {}
        for level in self.LEVELS:
            buckets: Dict[Tuple, List[float]] = {}
            for work in works:
                value = getattr(work, metric, None)
                if value is None:
                    continue
                key = tuple((getattr(work, dim) or "").strip().lower() for dim in level)
                if any(not part for part in key):
                    continue
                buckets.setdefault((level, key), []).append(float(value))
            for (group_level, key), values in buckets.items():
                self.groups[(group_level, key)] = PeerStats(
                    dict(zip(group_level, key)), metric, values)

    def best(self, work: Work, min_peers: int = 8) -> Optional[PeerStats]:
        fallback = None
        for level in self.LEVELS:
            key = tuple((getattr(work, dim) or "").strip().lower() for dim in level)
            stats = self.groups.get((level, key))
            if stats is None:
                continue
            if stats.peer_count >= min_peers:
                return stats
            fallback = fallback or stats
        return fallback

    def all_groups(self) -> List[Dict[str, Any]]:
        return [{"group_key": "|".join(f"{k}={v}" for k, v in stats.dimensions.items()),
                 **stats.to_dict()} for stats in self.groups.values()]


@dataclass
class Signal:
    rule_id: str
    name: str
    category: str
    severity: str
    method: str
    strength: float
    statement: str
    source_fields: Dict[str, Any]
    evidence: Dict[str, Any]
    recommended_actions: List[str]
    false_positive_notes: str
    rule_version: str
    related_work_ref: Optional[str] = None

    @property
    def contribution(self) -> float:
        return round(SEVERITY_CEILING[self.severity] * self.strength, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {"rule_id": self.rule_id, "name": self.name, "category": self.category,
                "category_label": CATEGORIES[self.category], "severity": self.severity,
                "method": self.method, "strength": round(self.strength, 3),
                "contribution": self.contribution, "statement": self.statement,
                "source_fields": self.source_fields, "evidence": self.evidence,
                "recommended_actions": list(self.recommended_actions),
                "false_positive_notes": self.false_positive_notes,
                "rule_version": self.rule_version, "related_work_ref": self.related_work_ref}


def ramp(value: float, trigger: float, saturate: float) -> float:
    if value <= trigger:
        return 0.0
    if saturate <= trigger:
        return 1.0
    return min(1.0, (value - trigger) / (saturate - trigger))


def build_signal(rule: RiskRule, strength: float, statement: str, source_fields: Dict[str, Any],
                 evidence: Dict[str, Any], related: Optional[str] = None) -> Signal:
    return Signal(rule.rule_id, rule.name, rule.category, rule.severity, rule.method,
                  max(0.0, min(1.0, strength)), statement, source_fields, evidence,
                  list(rule.recommended_actions), rule.false_positive_notes, rule.version,
                  related)


def char_ngrams(text: str, size: int = 4) -> Dict[str, int]:
    cleaned = re.sub(r"\s+", " ", normalise_description(text))
    counts: Dict[str, int] = {}
    for index in range(max(0, len(cleaned) - size + 1)):
        gram = cleaned[index:index + size]
        counts[gram] = counts.get(gram, 0) + 1
    return counts


def cosine(left: Dict[str, int], right: Dict[str, int]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(left[gram] * right[gram] for gram in set(left) & set(right))
    norm_left = math.sqrt(sum(value * value for value in left.values()))
    norm_right = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (norm_left * norm_right) if norm_left and norm_right else 0.0


def jaccard(left: set, right: set) -> float:
    return len(left & right) / len(left | right) if left and right else 0.0


class DuplicateIndex:
    """Similarity is semantic in intent, not exact string matching.

    Character 4-gram cosine is blended with token Jaccard overlap and blocked by
    district and category. SIMILARITY_BACKEND=embedding allows an operator to swap in
    sentence-transformers without touching the composer.
    """

    BACKEND = "lexical-char4gram+jaccard"

    def __init__(self, works: Sequence[Work]) -> None:
        self.blocks: Dict[Tuple[str, str], List[Tuple[Work, Dict[str, int], set]]] = {}
        for work in works:
            if not work.description:
                continue
            key = ((work.district or "").strip().lower(), (work.category or "").strip().lower())
            self.blocks.setdefault(key, []).append(
                (work, char_ngrams(work.description), description_tokens(work.description)))

    def best_match(self, work: Work) -> Optional[Tuple[Work, float, float, float]]:
        if not work.description:
            return None
        key = ((work.district or "").strip().lower(), (work.category or "").strip().lower())
        grams, tokens = char_ngrams(work.description), description_tokens(work.description)
        best = None
        for other, other_grams, other_tokens in self.blocks.get(key, []):
            if other.work_id == work.work_id:
                continue
            cos, jac = cosine(grams, other_grams), jaccard(tokens, other_tokens)
            blended = 0.65 * cos + 0.35 * jac
            if best is None or blended > best[1]:
                best = (other, blended, cos, jac)
        return best


@dataclass
class DetectorContext:
    peers: PeerIndex
    duplicates: DuplicateIndex
    as_of: date
    active_rules: Dict[str, RiskRule]
    similarity_backend: str = DuplicateIndex.BACKEND
    gates: List[GateVerdict] = field(default_factory=list)

    def rule(self, rule_id: str) -> Optional[RiskRule]:
        return self.active_rules.get(rule_id)


def _fields(work: Work, names: Iterable[str]) -> Dict[str, Any]:
    payload = {}
    for name in names:
        value = getattr(work, name, None)
        payload[name] = value.isoformat() if isinstance(value, date) else value
    return payload


def detect_financial(work: Work, context: DetectorContext) -> List[Signal]:
    signals: List[Signal] = []
    rule = context.rule("FIN-COST-001")
    if rule:
        gate = evaluate_gating(work, rule)
        context.gates.append(gate)
        if gate.evaluated:
            stats = context.peers.best(work, int(rule.params["min_peers"]))
            robust = stats.robust_z(float(work.sanction_amount)) if stats else None
            if stats and robust is not None and robust > rule.params["trigger_z"]:
                strength = ramp(robust, rule.params["trigger_z"], rule.params["saturate_z"])
                if stats.peer_count < rule.params["min_peers"]:
                    strength *= 0.6
                signals.append(build_signal(
                    rule, strength,
                    f"Sanctioned amount {work.sanction_amount:,.0f} is {robust:.1f} robust "
                    f"standard deviations above the peer median {stats.median:,.0f} "
                    f"({stats.peer_count} comparable works).",
                    _fields(work, rule.evidence_fields),
                    stats.to_dict(float(work.sanction_amount))))
    rule = context.rule("FIN-UTIL-002")
    if rule:
        gate = evaluate_gating(work, rule)
        context.gates.append(gate)
        ratio = work.utilisation
        if gate.evaluated and ratio is not None and ratio > rule.params["trigger_ratio"]:
            signals.append(build_signal(
                rule, ramp(ratio, rule.params["trigger_ratio"], rule.params["saturate_ratio"]),
                f"Expenditure is {ratio * 100:.1f}% of the sanctioned amount.",
                _fields(work, rule.evidence_fields), {"utilisation_ratio": round(ratio, 4)}))
    return signals


def detect_execution(work: Work, context: DetectorContext) -> List[Signal]:
    signals: List[Signal] = []
    rule = context.rule("EXE-PROG-001")
    if rule:
        gate = evaluate_gating(work, rule)
        context.gates.append(gate)
        ratio = work.utilisation
        if gate.evaluated and ratio is not None and work.progress_percent is not None:
            gap = ratio * 100 - work.progress_percent
            if gap > rule.params["trigger_gap"]:
                signals.append(build_signal(
                    rule, ramp(gap, rule.params["trigger_gap"], rule.params["saturate_gap"]),
                    f"{ratio * 100:.1f}% of funds are reported spent against "
                    f"{work.progress_percent:.0f}% physical progress, a gap of {gap:.0f} points.",
                    _fields(work, rule.evidence_fields), {"gap_points": round(gap, 2)}))
    rule = context.rule("EXE-STAG-002")
    if rule:
        gate = evaluate_gating(work, rule)
        context.gates.append(gate)
        ratio = work.utilisation
        if (gate.evaluated and ratio is not None and work.progress_percent is not None
                and work.progress_percent <= rule.params["progress_ceiling"]
                and ratio > rule.params["trigger_ratio"]):
            signals.append(build_signal(
                rule, ramp(ratio, rule.params["trigger_ratio"], rule.params["saturate_ratio"]),
                f"{ratio * 100:.1f}% of funds are reported spent while progress is "
                f"{work.progress_percent:.0f}%.", _fields(work, rule.evidence_fields),
                {"utilisation_ratio": round(ratio, 4),
                 "progress_percent": work.progress_percent}))
    rule = context.rule("EXE-DELAY-003")
    if rule:
        gate = evaluate_gating(work, rule)
        context.gates.append(gate)
        overdue = work.days_overdue(context.as_of)
        if gate.evaluated and overdue and overdue > rule.params["trigger_days"]:
            signals.append(build_signal(
                rule, ramp(overdue, rule.params["trigger_days"], rule.params["saturate_days"]),
                f"The work is {overdue} days past its expected completion date.",
                _fields(work, rule.evidence_fields), {"days_overdue": overdue}))
    return signals


def detect_duplicate(work: Work, context: DetectorContext) -> List[Signal]:
    rule = context.rule("DUP-SIM-001")
    if not rule:
        return []
    gate = evaluate_gating(work, rule)
    context.gates.append(gate)
    if not gate.evaluated:
        return []
    match = context.duplicates.best_match(work)
    if not match or match[1] <= rule.params["trigger_similarity"]:
        return []
    other, blended, cos, jac = match
    return [build_signal(
        rule, ramp(blended, rule.params["trigger_similarity"],
                   rule.params["saturate_similarity"]),
        f"Description is {blended * 100:.0f}% similar to work {other.work_id} in the same "
        "district and category.", _fields(work, rule.evidence_fields),
        {"similarity": round(blended, 3), "cosine": round(cos, 3), "jaccard": round(jac, 3),
         "backend": context.similarity_backend, "matched_work": other.work_id,
         "matched_description": other.description,
         "matched_sanction_amount": other.sanction_amount}, other.work_id)]


def detect_compliance(work: Work, context: DetectorContext) -> List[Signal]:
    signals: List[Signal] = []
    rule = context.rule("CMP-DATA-001")
    if rule:
        missing = [name for name in MANDATORY_FIELDS if getattr(work, name, None) in (None, "")]
        context.gates.append(GateVerdict(rule.rule_id, True))
        if len(missing) >= rule.params["trigger_missing"]:
            signals.append(build_signal(
                rule, ramp(len(missing), rule.params["trigger_missing"] - 1,
                           rule.params["saturate_missing"]),
                f"{len(missing)} mandatory field(s) are missing: {', '.join(missing)}.",
                {"missing_fields": missing}, {"missing_fields": missing}))
    rule = context.rule("CMP-CHRON-002")
    if rule:
        gate = evaluate_gating(work, rule)
        context.gates.append(gate)
        if gate.evaluated:
            violations = []
            if work.expected_completion and work.sanction_date > work.expected_completion:
                violations.append("expected completion precedes sanction")
            if work.actual_completion and work.sanction_date > work.actual_completion:
                violations.append("actual completion precedes sanction")
            if work.actual_completion and work.actual_completion > context.as_of:
                violations.append("completion date is in the future")
            if (work.actual_completion and work.progress_percent is not None
                    and work.progress_percent < 100):
                violations.append("completion recorded while progress is below 100%")
            if violations:
                signals.append(build_signal(
                    rule, min(1.0, len(violations) * rule.params["per_violation"]),
                    "Date fields contradict each other: " + "; ".join(violations) + ".",
                    _fields(work, rule.evidence_fields), {"violations": violations}))
    return signals


def detect_predictive(work: Work, context: DetectorContext) -> List[Signal]:
    rule = context.rule("PRD-TRAJ-001")
    if not rule:
        return []
    gate = evaluate_gating(work, rule)
    context.gates.append(gate)
    if not gate.evaluated or work.actual_completion is not None:
        return []
    elapsed = (context.as_of - work.sanction_date).days
    total = (work.expected_completion - work.sanction_date).days
    if elapsed <= 30 or total <= 0:
        return []
    projected = min(100.0, (work.progress_percent or 0.0) / elapsed * total)
    shortfall = 100.0 - projected
    if shortfall <= rule.params["trigger_shortfall"]:
        return []
    return [build_signal(
        rule, ramp(shortfall, rule.params["trigger_shortfall"],
                   rule.params["saturate_shortfall"]),
        f"At the reported pace the work reaches about {projected:.0f}% by its expected "
        f"completion date, a shortfall of {shortfall:.0f} points.",
        _fields(work, rule.evidence_fields),
        {"projected_completion_percent": round(projected, 1),
         "shortfall_points": round(shortfall, 1), "methodology": PREDICTIVE_METHODOLOGY})]


DETECTORS: Tuple[Callable[[Work, DetectorContext], List[Signal]], ...] = (
    detect_financial, detect_execution, detect_duplicate, detect_compliance, detect_predictive)

DIMENSION_WEIGHTS = {"completeness": 0.40, "validity": 0.25, "consistency": 0.20,
                     "timeliness": 0.15}


def record_quality(row: Dict[str, Any], work: Work, as_of: date) -> Dict[str, Any]:
    missing = [name for name in MANDATORY_FIELDS if getattr(work, name, None) in (None, "")]
    completeness = 1.0 - len(missing) / len(MANDATORY_FIELDS)
    invalid = checked = 0
    issues: List[str] = []
    for name in NUMERIC_FIELDS + DATE_FIELDS:
        raw = row.get(name)
        if raw in (None, ""):
            continue
        checked += 1
        if getattr(work, name, None) is None:
            invalid += 1
            issues.append(f"{name} could not be parsed from '{raw}'")
        elif name in NUMERIC_FIELDS and (getattr(work, name) or 0) < 0:
            invalid += 1
            issues.append(f"{name} is negative")
    validity = 1.0 if checked == 0 else 1.0 - invalid / checked
    inconsistencies = 0
    if (work.sanction_date and work.expected_completion
            and work.sanction_date > work.expected_completion):
        inconsistencies += 1
        issues.append("expected completion precedes sanction date")
    if work.progress_percent is not None and not 0 <= work.progress_percent <= 100:
        inconsistencies += 1
        issues.append("progress percent outside 0-100")
    if work.utilisation is not None and work.utilisation > 1.5:
        inconsistencies += 1
        issues.append("expenditure far exceeds sanction")
    consistency = max(0.0, 1.0 - inconsistencies * 0.34)
    if work.sanction_date is None:
        timeliness = 0.5
        issues.append("sanction date missing, freshness cannot be assessed")
    else:
        age = (as_of - work.sanction_date).days
        timeliness = 1.0 if age <= 540 else max(0.3, 1.0 - (age - 540) / 1460)
    dimensions = {"completeness": round(completeness, 4), "validity": round(validity, 4),
                  "consistency": round(consistency, 4), "timeliness": round(timeliness, 4)}
    score = sum(dimensions[key] * weight for key, weight in DIMENSION_WEIGHTS.items()) * 100
    return {"score": round(score, 2), "dimensions": dimensions, "missing_fields": missing,
            "issues": issues, "quality_version": QUALITY_VERSION, "note": QUALITY_NOTE}


def dataset_quality(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {"score": 0.0, "dimensions": {}, "records": 0,
                "quality_version": QUALITY_VERSION, "note": QUALITY_NOTE}
    dimensions = {key: round(sum(item["dimensions"][key] for item in records) / len(records), 4)
                  for key in DIMENSION_WEIGHTS}
    score = sum(dimensions[key] * weight for key, weight in DIMENSION_WEIGHTS.items()) * 100
    gaps: Dict[str, int] = {}
    for item in records:
        for name in item["missing_fields"]:
            gaps[name] = gaps.get(name, 0) + 1
    return {"score": round(score, 2), "dimensions": dimensions, "records": len(records),
            "field_gaps": gaps, "quality_version": QUALITY_VERSION, "note": QUALITY_NOTE}


RISK_BANDS = ((70.0, "HIGH"), (40.0, "MEDIUM"), (0.0, "LOW"))
CATEGORY_CEILING = {"FIN": 40.0, "EXE": 40.0, "DUP": 30.0, "CMP": 15.0, "PRD": 25.0}
DEFAULT_CATEGORY_WEIGHTS = {key: 1.0 for key in CATEGORIES}
CONFIDENCE_WEIGHTS = {"field_completeness": 0.30, "method_strength": 0.25, "peer_support": 0.20,
                      "corroboration": 0.15, "record_quality": 0.10}
METHOD_STRENGTH = {
    "deterministic ratio threshold": 1.0,
    "deterministic gap between utilisation and progress": 0.95,
    "deterministic threshold on utilisation with low progress": 0.9,
    "deterministic date arithmetic": 1.0,
    "deterministic date consistency check": 1.0,
    "deterministic completeness check": 1.0,
    "robust-z (median/MAD) against contextual peer group": 0.8,
    "character n-gram cosine blended with token Jaccard similarity": 0.7,
    "unsupervised linear extrapolation": 0.55,
}
DEFAULT_PRIORITY_WEIGHTS = {"risk": 0.45, "confidence": 0.20, "impact": 0.15, "urgency": 0.12,
                            "actionability": 0.08}
DEFAULT_PRIORITY_BANDS = {"P1": 68.0, "P2": 45.0}
PRIORITY_LABELS = {"P1": "P1 - VERIFY FIRST", "P2": "P2 - REVIEW", "P3": "P3 - MONITOR"}
DUE_DAYS_BY_PRIORITY = {"P1": 3, "P2": 10, "P3": 30}
ACTIONABLE = {"FIN", "EXE", "DUP"}


def band_for(score: float) -> str:
    for threshold, label in RISK_BANDS:
        if score >= threshold:
            return label
    return "LOW"


def compose(signals: Sequence[Signal], category_weights: Optional[Dict[str, float]] = None,
            rule_weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    weights = {**DEFAULT_CATEGORY_WEIGHTS, **(category_weights or {})}
    rule_weights = rule_weights or {}
    category_scores = {key: 0.0 for key in CATEGORIES}
    factors = []
    for signal in signals:
        contribution = signal.contribution * rule_weights.get(signal.rule_id, 1.0)
        category_scores[signal.category] += contribution
        factors.append({**signal.to_dict(), "weighted_contribution": round(contribution, 2)})
    for key in category_scores:
        category_scores[key] = round(min(CATEGORY_CEILING[key], category_scores[key]), 2)
    score = round(min(100.0, sum(category_scores[key] * weights.get(key, 1.0)
                                 for key in category_scores)), 2)
    factors.sort(key=lambda item: item["weighted_contribution"], reverse=True)
    return {"risk_score": score, "risk_band": band_for(score),
            "category_scores": category_scores, "factors": factors,
            "composer_version": COMPOSER_VERSION}


def compute_confidence(work: Work, signals: Sequence[Signal], quality: Dict[str, Any],
                       peer_stats: Optional[PeerStats],
                       evidence_count: int = 0) -> Dict[str, Any]:
    present = sum(1 for name in MANDATORY_FIELDS if getattr(work, name, None) not in (None, ""))
    completeness = present / len(MANDATORY_FIELDS)
    strengths = [METHOD_STRENGTH.get(signal.method, 0.6) for signal in signals]
    method_strength = sum(strengths) / len(strengths) if strengths else 0.4
    peer_support = 0.35 if peer_stats is None else min(1.0, 0.35 + peer_stats.peer_count / 40)
    distinct = len({signal.category for signal in signals})
    corroboration = min(1.0, 0.3 + 0.25 * distinct + (0.1 if evidence_count else 0.0))
    components = {"field_completeness": round(completeness, 3),
                  "method_strength": round(method_strength, 3),
                  "peer_support": round(peer_support, 3),
                  "corroboration": round(corroboration, 3),
                  "record_quality": round(min(1.0, quality.get("score", 0.0) / 100), 3)}
    score = round(sum(components[key] * CONFIDENCE_WEIGHTS[key] for key in components) * 100, 2)
    notes = []
    if completeness < 1.0:
        notes.append("Some mandatory fields are missing, which lowers confidence.")
    if peer_stats is not None and peer_stats.peer_count < 8:
        notes.append(f"Only {peer_stats.peer_count} comparable works were available for "
                     "benchmarking.")
    if not signals:
        notes.append("No rule fired for this work.")
    notes.append(QUALITY_NOTE)
    return {"confidence_score": score, "confidence_factors": components,
            "confidence_notes": notes, "confidence_version": CONFIDENCE_VERSION}


def interpret(risk_score: float, confidence: float) -> str:
    if confidence >= 70:
        strength = "The underlying data supports these signals."
    elif confidence >= 50:
        strength = "Confidence is moderate; verify the underlying record."
    else:
        strength = "Confidence is low, mainly because of data gaps."
    return (f"{band_for(risk_score).title()} risk ({risk_score:.1f}/100) with "
            f"{confidence:.1f}/100 confidence. {strength} {TRANSPARENCY_NOTE}")


def compute_priority(work: Work, composition: Dict[str, Any], confidence: float,
                     signals: Sequence[Signal], max_amount: float, as_of: date,
                     weights: Optional[Dict[str, float]] = None,
                     bands: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    weights = {**DEFAULT_PRIORITY_WEIGHTS, **(weights or {})}
    bands = {**DEFAULT_PRIORITY_BANDS, **(bands or {})}
    impact = 0.0
    if work.sanction_amount and max_amount > 0:
        impact = min(1.0, math.log10(1 + work.sanction_amount) / math.log10(1 + max_amount))
    overdue = work.days_overdue(as_of) or 0
    urgency = min(1.0, overdue / 540) if overdue else (0.25 if work.actual_completion is None
                                                       else 0.0)
    actionability = min(1.0, sum(1 for signal in signals
                                 if signal.category in ACTIONABLE) / 3)
    components = {"risk": round(composition["risk_score"] / 100, 3),
                  "confidence": round(confidence / 100, 3), "impact": round(impact, 3),
                  "urgency": round(urgency, 3), "actionability": round(actionability, 3)}
    index = round(sum(components[key] * weights[key] for key in components) * 100, 2)
    priority = "P1" if index >= bands["P1"] else "P2" if index >= bands["P2"] else "P3"
    rationale = [f"{label} contributes {components[key] * weights[key] * 100:.1f} of the index"
                 for key, label in (("risk", "Risk"), ("confidence", "Confidence"),
                                    ("impact", "Financial impact"), ("urgency", "Time pressure"),
                                    ("actionability", "Actionability"))]
    return {"priority": priority, "priority_label": PRIORITY_LABELS[priority],
            "priority_index": index, "priority_components": components,
            "priority_rationale": rationale, "priority_version": PRIORITY_VERSION,
            "due_days": DUE_DAYS_BY_PRIORITY[priority]}


@dataclass
class WorkAnalysis:
    work: Work
    signals: List[Signal]
    composition: Dict[str, Any]
    confidence: Dict[str, Any]
    priority: Dict[str, Any]
    quality: Dict[str, Any]
    peer_stats: Optional[PeerStats]
    gates: List[GateVerdict]
    features: Dict[str, Any]

    @property
    def recommended_actions(self) -> List[str]:
        actions: List[str] = []
        for signal in sorted(self.signals, key=lambda item: item.contribution, reverse=True):
            for action in signal.recommended_actions:
                if action not in actions:
                    actions.append(action)
        return actions or ["No rule fired. Keep this work under routine monitoring."]


@dataclass
class PopulationAnalysis:
    results: List[WorkAnalysis]
    dataset_quality: Dict[str, Any]
    peer_groups: List[Dict[str, Any]]
    availability: Dict[str, str]
    similarity_backend: str
    engine_version: str = ENGINE_VERSION
    ontology_version: str = ONTOLOGY_VERSION


def analyse_population(rows: Sequence[Dict[str, Any]],
                       active_rules: Optional[Sequence[RiskRule]] = None,
                       category_weights: Optional[Dict[str, float]] = None,
                       similarity_backend: str = "lexical",
                       evidence_counts: Optional[Dict[str, int]] = None,
                       as_of: Optional[date] = None) -> PopulationAnalysis:
    as_of = as_of or datetime.now(timezone.utc).date()
    rules = {rule.rule_id: rule for rule in (active_rules or RULES)}
    rule_weights = {rule.rule_id: rule.weight for rule in rules.values()}
    works = [Work.from_row(row) for row in rows]
    peers, duplicates = PeerIndex(works), DuplicateIndex(works)
    if similarity_backend == "lexical":
        backend = DuplicateIndex.BACKEND
    else:
        backend = (f"{similarity_backend} (requested; falls back to {DuplicateIndex.BACKEND} "
                   "unless sentence-transformers is installed)")
    max_amount = max([work.sanction_amount or 0.0 for work in works] or [0.0])
    evidence_counts = evidence_counts or {}
    results, quality_records = [], []
    for row, work in zip(rows, works):
        context = DetectorContext(peers, duplicates, as_of, rules, backend)
        signals: List[Signal] = []
        for detector in DETECTORS:
            signals.extend(detector(work, context))
        quality = record_quality(row, work, as_of)
        quality_records.append(quality)
        composition = compose(signals, category_weights, rule_weights)
        peer_stats = peers.best(work)
        confidence = compute_confidence(work, signals, quality, peer_stats,
                                        evidence_counts.get(work.work_id, 0))
        priority = compute_priority(work, composition, confidence["confidence_score"], signals,
                                    max_amount, as_of)
        results.append(WorkAnalysis(work, signals, composition, confidence, priority, quality,
                                    peer_stats, context.gates, work.feature_snapshot(as_of)))
    return PopulationAnalysis(results, dataset_quality(quality_records), peers.all_groups(),
                              field_availability(rows), backend)
