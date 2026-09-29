# Risk engine

Deterministic and model-independent. Given the same rows, rules and weights it produces the
same numbers every time.

## Signal ontology (versioned, stored in `risk_rules`)

| ID | Family | Severity | Method |
| --- | --- | --- | --- |
| FIN-COST-001 | Financial | HIGH | Robust z (median/MAD) against a contextual peer group |
| FIN-UTIL-002 | Financial | HIGH | Expenditure over sanctioned amount |
| EXE-PROG-001 | Execution | HIGH | Utilisation minus reported physical progress |
| EXE-STAG-002 | Execution | MEDIUM | Funds released while progress is at or near zero |
| EXE-DELAY-003 | Execution | MEDIUM | Days past expected completion |
| DUP-SIM-001 | Duplication | HIGH | Char 4-gram cosine blended with token Jaccard, blocked by district and category |
| CMP-DATA-001 | Compliance | MEDIUM | Missing mandatory fields |
| CMP-CHRON-002 | Compliance | MEDIUM | Chronologically impossible dates |
| PRD-TRAJ-001 | Early warning | MEDIUM | Unsupervised linear extrapolation of reported progress |

Each rule is gated: if a required field is missing the rule is **not evaluated**, and the
dossier states which fields were missing. A rule never fires on absent data.

Duplicate detection is semantic-ish rather than exact string matching, and the backend is
swappable (`SIMILARITY_BACKEND=lexical|embedding`); the lexical backend ships by default so
the product works with no model downloads.

## Peer benchmarking

Peer groups are contextual and tried in order: category within district, category within
state, then category nationally. The first group with at least eight peers wins; a smaller
group is still used but its signal strength is discounted. Dossiers show the current value,
peer median, percentile and peer count.

## Composition

Contribution = severity ceiling (LOW 10, MEDIUM 20, HIGH 30) x strength x rule weight.
Contributions are summed per family, capped per family (FIN 40, EXE 40, DUP 30, CMP 15,
PRD 25), multiplied by configurable family weights, then capped at 100.
Bands: HIGH >= 70, MEDIUM >= 40, otherwise LOW.

## Confidence (separate from risk)

Weighted blend of field completeness (0.30), method strength (0.25), peer support (0.20),
corroboration across families and evidence (0.15) and record quality (0.10).

> Missing data is not treated as normal. Low data quality reduces the confidence attached to a
> risk result instead of raising or lowering risk.

## Verification priority index

A different number from risk: risk 0.45, confidence 0.20, financial impact 0.15, time
pressure 0.12, actionability 0.08. Bands: P1 - VERIFY FIRST >= 68, P2 - REVIEW >= 45,
otherwise P3 - MONITOR. P1 cases are due in 3 days, P2 in 10, P3 in 30.

## Calibration

Case outcomes mark each contributing signal as confirmed useful, not useful, pending or a data
problem, and feed alert precision and false-positive metrics.

> Controlled outcome feedback for future calibration and model development. No model is
> retrained automatically from these outcomes.
