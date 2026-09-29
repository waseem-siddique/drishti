"""Business services: rule config, analysis persistence, dossiers, cases, analytics."""
from __future__ import annotations
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from sqlalchemy import case, desc, func, select
from sqlalchemy.orm import Session
from . import audit, risk
from .models import (CaseAssignment, CaseNote, CaseStatusHistory, DataQualityResult, Dataset,
                     Evidence, ModelVersion, Notification, PeerGroup, RiskRule, RiskRuleVersion,
                     RiskScore, RiskSignal, STATUS_TRANSITIONS, SystemConfig, User,
                     VerificationCase, Work, utcnow)
from .repositories import apply_scope, serialise_row

WEIGHT_CONFIG_KEY = "risk.weights"
DEFAULT_WEIGHT_VERSION = "1.0"
CALIBRATION_NOTE = ("Controlled outcome feedback for future calibration and model development. "
                    "No model is retrained automatically from these outcomes.")
AUTHENTICITY_NOTE = ("A SHA-256 checksum was recorded at upload. Uploading a document does not "
                     "establish its authenticity.")
OUTCOME_USEFULNESS = {"VALID_ANOMALY": "CONFIRMED_USEFUL", "ESCALATED": "CONFIRMED_USEFUL",
                      "NEEDS_FIELD_VERIFICATION": "PENDING", "FALSE_POSITIVE": "NOT_USEFUL",
                      "NO_ISSUE_FOUND": "NOT_USEFUL", "DATA_ISSUE": "DATA_PROBLEM"}


class CaseError(Exception):
    pass


# ---------------------------------------------------------------- rule configuration
def sync_rules(session: Session) -> None:
    """Seed the versioned rule ontology into the database on first start."""
    for rule in risk.RULES:
        row = session.scalar(select(RiskRule).where(RiskRule.rule_id == rule.rule_id))
        if row is None:
            session.add(RiskRule(
                rule_id=rule.rule_id, name=rule.name, category=rule.category,
                severity=rule.severity, description=rule.description, method=rule.method,
                required_fields=list(rule.required_fields),
                evidence_fields=list(rule.evidence_fields),
                recommended_actions=list(rule.recommended_actions),
                false_positive_notes=rule.false_positive_notes, params=dict(rule.params),
                weight=rule.weight, is_active=True, version=rule.version))
    for component, version, methodology in (
            ("engine", risk.ENGINE_VERSION, "Deterministic rules and statistical detectors."),
            ("composer", risk.COMPOSER_VERSION, "Category-capped weighted composition."),
            ("confidence", risk.CONFIDENCE_VERSION, "Evidence and data quality weighting."),
            ("priority", risk.PRIORITY_VERSION, "Verification priority index."),
            ("ontology", risk.ONTOLOGY_VERSION, "Versioned signal ontology.")):
        exists = session.scalar(select(ModelVersion).where(
            ModelVersion.component == component, ModelVersion.version == version))
        if exists is None:
            session.add(ModelVersion(component=component, version=version,
                                     methodology=methodology))
    if session.scalar(select(SystemConfig).where(SystemConfig.key == WEIGHT_CONFIG_KEY)) is None:
        session.add(SystemConfig(key=WEIGHT_CONFIG_KEY,
                                 value={"categories": risk.DEFAULT_CATEGORY_WEIGHTS,
                                        "priority": risk.DEFAULT_PRIORITY_WEIGHTS,
                                        "priority_bands": risk.DEFAULT_PRIORITY_BANDS},
                                 version=DEFAULT_WEIGHT_VERSION,
                                 description="Risk composer and priority weights."))
    session.commit()


def active_rule_specs(session: Session) -> List[risk.RiskRule]:
    specs = []
    for row in session.scalars(select(RiskRule).where(RiskRule.is_active.is_(True))).all():
        base = risk.RULES_BY_ID.get(row.rule_id)
        if base is None:
            continue
        params = {**base.params, **(row.params or {})}
        specs.append(risk.RiskRule(base.rule_id, row.name or base.name, base.category,
                                   row.severity or base.severity, row.description or base.description,
                                   base.method, base.required_fields, base.evidence_fields,
                                   tuple(row.recommended_actions or base.recommended_actions),
                                   row.false_positive_notes or base.false_positive_notes, params,
                                   row.weight if row.weight is not None else base.weight,
                                   row.version or base.version))
    return specs or list(risk.RULES)


def weight_config(session: Session) -> SystemConfig:
    return session.scalar(select(SystemConfig).where(SystemConfig.key == WEIGHT_CONFIG_KEY))


def serialise_rule(row: RiskRule) -> Dict[str, Any]:
    return {"rule_id": row.rule_id, "name": row.name, "category": row.category,
            "category_label": risk.CATEGORIES.get(row.category, row.category),
            "severity": row.severity, "description": row.description, "method": row.method,
            "required_fields": row.required_fields, "evidence_fields": row.evidence_fields,
            "recommended_actions": row.recommended_actions,
            "false_positive_notes": row.false_positive_notes, "params": row.params,
            "weight": row.weight, "is_active": row.is_active, "version": row.version,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


def update_rule(session: Session, actor, rule_id: str, payload: Dict[str, Any],
                ip: Optional[str] = None) -> Dict[str, Any]:
    row = session.scalar(select(RiskRule).where(RiskRule.rule_id == rule_id))
    if row is None:
        raise CaseError(f"Rule {rule_id} does not exist.")
    previous = serialise_rule(row)
    if payload.get("is_active") is not None:
        row.is_active = bool(payload["is_active"])
    if payload.get("weight") is not None:
        row.weight = float(payload["weight"])
    if payload.get("params"):
        row.params = {**(row.params or {}), **payload["params"]}
    major, _, minor = (row.version or "1.0").partition(".")
    row.version = f"{major}.{int(minor or 0) + 1}"
    row.modified_by_id = actor.id
    session.add(RiskRuleVersion(rule_pk=row.id, version=row.version,
                                payload=serialise_rule(row),
                                change_note=payload.get("change_note"), changed_by_id=actor.id))
    audit.record(session, "RULE_UPDATED", actor, "risk_rule", rule_id, previous,
                 serialise_rule(row), ip)
    session.commit()
    return serialise_rule(row)


# ---------------------------------------------------------------- analysis
def canonical_rows(session: Session) -> List[Dict[str, Any]]:
    rows = []
    for work in session.scalars(select(Work)).all():
        rows.append({"work_id": work.work_id, "description": work.description,
                     "state": work.state, "district": work.district,
                     "constituency": work.constituency, "category": work.category,
                     "agency": work.agency, "sanction_amount": work.sanction_amount,
                     "expenditure": work.expenditure,
                     "progress_percent": work.progress_percent,
                     "sanction_date": work.sanction_date,
                     "expected_completion": work.expected_completion,
                     "actual_completion": work.actual_completion, "status": work.status,
                     "latitude": work.latitude, "longitude": work.longitude})
    return rows


def _evidence_counts(session: Session) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for work_pk, total in session.execute(
            select(Evidence.work_pk, func.count()).group_by(Evidence.work_pk)).all():
        work = session.get(Work, work_pk) if work_pk else None
        if work:
            counts[work.work_id] = int(total)
    return counts


def analyse_dataset(session: Session, actor=None, ip: Optional[str] = None) -> Dict[str, Any]:
    """Run the deterministic engine over every stored work and persist the results."""
    rows = canonical_rows(session)
    if not rows:
        raise CaseError("There are no works to analyse. Upload a dataset first.")
    config = weight_config(session)
    weights = (config.value or {}).get("categories") if config else None
    from .config import get_settings
    analysis = risk.analyse_population(rows, active_rule_specs(session), weights,
                                       get_settings().similarity_backend,
                                       _evidence_counts(session))
    works = {work.work_id: work for work in session.scalars(select(Work)).all()}
    session.query(RiskSignal).delete()
    session.query(RiskScore).delete()
    session.query(DataQualityResult).delete()
    session.query(PeerGroup).delete()
    dataset = session.scalars(select(Dataset).order_by(desc(Dataset.id))).first()
    for result in analysis.results:
        work = works.get(result.work.work_id)
        if work is None:
            continue
        session.add(RiskScore(
            work_id=work.id, risk_score=result.composition["risk_score"],
            risk_band=result.composition["risk_band"],
            confidence_score=result.confidence["confidence_score"],
            confidence_factors=result.confidence["confidence_factors"],
            confidence_notes=result.confidence["confidence_notes"],
            interpretation=risk.interpret(result.composition["risk_score"],
                                          result.confidence["confidence_score"]),
            priority=result.priority["priority"],
            priority_label=result.priority["priority_label"],
            priority_index=result.priority["priority_index"],
            priority_components=result.priority["priority_components"],
            priority_rationale=result.priority["priority_rationale"],
            category_scores=result.composition["category_scores"],
            recommended_actions=result.recommended_actions,
            factors=result.composition["factors"], features=result.features,
            engine_version=risk.ENGINE_VERSION, ontology_version=risk.ONTOLOGY_VERSION,
            weight_version=config.version if config else DEFAULT_WEIGHT_VERSION,
            rule_versions={rule.rule_id: rule.version for rule in active_rule_specs(session)},
            similarity_backend=analysis.similarity_backend))
        for signal in result.signals:
            payload = signal.to_dict()
            session.add(RiskSignal(
                work_id=work.id, rule_id=signal.rule_id, name=signal.name,
                category=signal.category, severity=signal.severity, method=signal.method,
                strength=signal.strength, statement=signal.statement,
                source_fields=payload["source_fields"], evidence=payload["evidence"],
                recommended_actions=payload["recommended_actions"],
                false_positive_notes=signal.false_positive_notes,
                rule_version=signal.rule_version, related_work_ref=signal.related_work_ref))
        session.add(DataQualityResult(
            dataset_id=dataset.id if dataset else None, work_id=work.id, scope="RECORD",
            score=result.quality["score"], dimensions=result.quality["dimensions"],
            missing_fields=result.quality["missing_fields"], issues=result.quality["issues"],
            quality_version=risk.QUALITY_VERSION))
    session.add(DataQualityResult(
        dataset_id=dataset.id if dataset else None, scope="DATASET",
        score=analysis.dataset_quality["score"],
        dimensions=analysis.dataset_quality["dimensions"],
        missing_fields=list((analysis.dataset_quality.get("field_gaps") or {}).keys()),
        issues=[analysis.dataset_quality["note"]], quality_version=risk.QUALITY_VERSION))
    for group in analysis.peer_groups:
        session.add(PeerGroup(dataset_id=dataset.id if dataset else None,
                              group_key=group["group_key"], dimensions=group["dimensions"],
                              metric=group["metric"], peer_count=group["peer_count"],
                              median_value=group["median"], p25_value=group["p25"],
                              p75_value=group["p75"]))
    if actor is not None:
        audit.record(session, "RISK_ANALYSIS", actor, "dataset",
                     str(dataset.id) if dataset else "all", None,
                     {"works": len(analysis.results),
                      "engine_version": risk.ENGINE_VERSION,
                      "dataset_quality": analysis.dataset_quality["score"]}, ip)
    session.commit()
    return {"works_analysed": len(analysis.results),
            "dataset_quality": analysis.dataset_quality,
            "similarity_backend": analysis.similarity_backend,
            "field_availability": analysis.availability,
            "engine_version": risk.ENGINE_VERSION, "ontology_version": risk.ONTOLOGY_VERSION,
            "transparency_note": risk.TRANSPARENCY_NOTE}


def peer_context(session: Session, work: Work) -> Optional[Dict[str, Any]]:
    if not work.category:
        return None
    keys = [f"category={(work.category or '').lower()}|district={(work.district or '').lower()}",
            f"category={(work.category or '').lower()}|state={(work.state or '').lower()}",
            f"category={(work.category or '').lower()}"]
    for key in keys:
        group = session.scalar(select(PeerGroup).where(PeerGroup.group_key == key))
        if group and group.peer_count:
            return {"group_key": group.group_key, "dimensions": group.dimensions,
                    "metric": group.metric, "peer_count": group.peer_count,
                    "median": group.median_value, "p25": group.p25_value,
                    "p75": group.p75_value, "value": work.sanction_amount}
    return None


def dossier(session: Session, work: Work) -> Dict[str, Any]:
    score = work.risk_score
    quality = work.quality_result
    signals = session.scalars(select(RiskSignal).where(RiskSignal.work_id == work.id)).all()
    case_row = session.scalars(select(VerificationCase).where(
        VerificationCase.work_pk == work.id).order_by(desc(VerificationCase.id))).first()
    evidence = session.scalars(select(Evidence).where(Evidence.work_pk == work.id)).all()
    return {
        "work_id": work.work_id, "work": serialise_row(work, score),
        "risk": ({"risk_score": score.risk_score, "risk_band": score.risk_band,
                  "confidence_score": score.confidence_score,
                  "confidence_factors": score.confidence_factors,
                  "confidence_notes": score.confidence_notes,
                  "interpretation": score.interpretation, "priority": score.priority,
                  "priority_label": score.priority_label,
                  "priority_index": score.priority_index,
                  "priority_components": score.priority_components,
                  "priority_rationale": score.priority_rationale,
                  "category_scores": score.category_scores,
                  "recommended_actions": score.recommended_actions,
                  "engine_version": score.engine_version,
                  "ontology_version": score.ontology_version,
                  "weight_version": score.weight_version, "rule_versions": score.rule_versions,
                  "similarity_backend": score.similarity_backend,
                  "analysed_at": score.analysed_at.isoformat() if score.analysed_at else None}
                 if score else None),
        "factors": (score.factors if score else []) or [],
        "signals": [{"rule_id": item.rule_id, "name": item.name, "category": item.category,
                     "severity": item.severity, "method": item.method,
                     "statement": item.statement, "source_fields": item.source_fields,
                     "evidence": item.evidence,
                     "recommended_actions": item.recommended_actions,
                     "false_positive_notes": item.false_positive_notes,
                     "rule_version": item.rule_version,
                     "related_work_ref": item.related_work_ref} for item in signals],
        "peer_benchmark": peer_context(session, work),
        "data_quality": ({"score": quality.score, "dimensions": quality.dimensions,
                          "missing_fields": quality.missing_fields, "issues": quality.issues,
                          "note": risk.QUALITY_NOTE} if quality else None),
        "case": serialise_case(case_row) if case_row else None,
        "evidence": [serialise_evidence(item) for item in evidence],
        "unavailable_fields": [name for name in risk.CANONICAL_FIELDS
                               if getattr(work, name, None) in (None, "")],
        "no_data_label": risk.NO_DATA, "transparency_note": risk.TRANSPARENCY_NOTE,
    }


# ---------------------------------------------------------------- cases
def next_case_ref(session: Session) -> str:
    year = date.today().year
    total = session.scalar(select(func.count()).select_from(VerificationCase)) or 0
    return f"VC-{year}-{total + 1:05d}"


def build_checklist(score: Optional[RiskScore]) -> List[Dict[str, Any]]:
    items = ["Confirm the record matches the sanction order",
             "Confirm the reported expenditure against vouchers"]
    for action in (score.recommended_actions if score else []) or []:
        if action not in items:
            items.append(action)
    return [{"id": index + 1, "label": label, "done": False} for index, label in enumerate(items)]


def serialise_case(row: VerificationCase) -> Dict[str, Any]:
    return {"case_ref": row.case_ref, "work_ref": row.work_ref, "status": row.status,
            "priority": row.priority, "risk_score": row.risk_score,
            "confidence_score": row.confidence_score, "categories": row.categories,
            "signal_rule_ids": row.signal_rule_ids,
            "recommended_actions": row.recommended_actions, "checklist": row.checklist,
            "outcome": row.outcome, "outcome_note": row.outcome_note,
            "outcome_recorded_at": (row.outcome_recorded_at.isoformat()
                                    if row.outcome_recorded_at else None),
            "assigned_to": ({"id": row.assigned_to.id, "full_name": row.assigned_to.full_name,
                             "role": row.assigned_to.role} if row.assigned_to else None),
            "created_by": row.created_by.full_name if row.created_by else None,
            "due_date": row.due_date.isoformat() if row.due_date else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "allowed_transitions": sorted(STATUS_TRANSITIONS.get(row.status, set())),
            "calibration_note": CALIBRATION_NOTE}


def serialise_evidence(row: Evidence) -> Dict[str, Any]:
    return {"id": row.id, "filename": row.original_filename, "doc_type": row.doc_type,
            "size_bytes": row.size_bytes, "checksum_sha256": row.checksum_sha256,
            "uploaded_by": row.uploaded_by.full_name if row.uploaded_by else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "authenticity_note": AUTHENTICITY_NOTE}


def create_case(session: Session, actor, work: Work, note: Optional[str] = None,
                assign_to_id: Optional[int] = None, ip: Optional[str] = None) -> Dict[str, Any]:
    existing = session.scalar(select(VerificationCase).where(
        VerificationCase.work_pk == work.id, VerificationCase.status != "CLOSED"))
    if existing:
        raise CaseError(f"An open case ({existing.case_ref}) already exists for this work.")
    score = work.risk_score
    row = VerificationCase(
        case_ref=next_case_ref(session), work_pk=work.id, work_ref=work.work_id, status="OPEN",
        priority=score.priority if score else "P3",
        risk_score=score.risk_score if score else None,
        confidence_score=score.confidence_score if score else None,
        categories=list((score.category_scores or {}).keys()) if score else [],
        signal_rule_ids=[factor["rule_id"] for factor in (score.factors or [])] if score else [],
        recommended_actions=(score.recommended_actions if score else []) or [],
        checklist=build_checklist(score), created_by_id=actor.id,
        due_date=date.today() + timedelta(
            days=risk.DUE_DAYS_BY_PRIORITY.get(score.priority if score else "P3", 30)))
    session.add(row)
    session.flush()
    session.add(CaseStatusHistory(case_id=row.id, from_status=None, to_status="OPEN",
                                  note=note, changed_by_id=actor.id))
    if note:
        session.add(CaseNote(case_id=row.id, author_id=actor.id, body=note))
    audit.record(session, "CASE_CREATED", actor, "case", row.case_ref, None,
                 {"work_ref": work.work_id, "priority": row.priority}, ip)
    session.commit()
    if assign_to_id:
        return assign_case(session, actor, row, assign_to_id, None, ip)
    return serialise_case(row)


def assign_case(session: Session, actor, row: VerificationCase, assign_to_id: int,
                note: Optional[str], ip: Optional[str] = None) -> Dict[str, Any]:
    assignee = session.get(User, assign_to_id)
    if assignee is None or not assignee.is_active:
        raise CaseError("That user cannot be assigned work.")
    previous = serialise_case(row)
    row.assigned_to_id = assignee.id
    if row.status == "OPEN":
        session.add(CaseStatusHistory(case_id=row.id, from_status=row.status,
                                      to_status="ASSIGNED", note=note, changed_by_id=actor.id))
        row.status = "ASSIGNED"
    session.add(CaseAssignment(case_id=row.id, assigned_to_id=assignee.id,
                               assigned_by_id=actor.id, note=note))
    session.add(Notification(user_id=assignee.id, severity="WARN",
                             title=f"Case {row.case_ref} assigned to you",
                             body=f"Work {row.work_ref} - {row.priority}",
                             entity_type="case", entity_ref=row.case_ref))
    audit.record(session, "CASE_ASSIGNED", actor, "case", row.case_ref, previous,
                 {"assigned_to": assignee.email}, ip)
    session.commit()
    return serialise_case(row)


def change_status(session: Session, actor, row: VerificationCase, status: str,
                  note: Optional[str], ip: Optional[str] = None) -> Dict[str, Any]:
    allowed = STATUS_TRANSITIONS.get(row.status, set())
    if status not in allowed:
        raise CaseError(f"A case that is {row.status.replace('_', ' ').lower()} cannot move to "
                        f"{status.replace('_', ' ').lower()}.")
    previous = serialise_case(row)
    session.add(CaseStatusHistory(case_id=row.id, from_status=row.status, to_status=status,
                                  note=note, changed_by_id=actor.id))
    row.status = status
    if status in ("UNDER_REVIEW", "FIELD_VERIFICATION") and row.first_reviewed_at is None:
        row.first_reviewed_at = utcnow()
    if status == "CLOSED":
        row.closed_at = utcnow()
    audit.record(session, "CASE_STATUS_CHANGED", actor, "case", row.case_ref, previous,
                 {"status": status, "note": note}, ip)
    session.commit()
    return serialise_case(row)


def record_outcome(session: Session, actor, row: VerificationCase, outcome: str,
                   note: Optional[str], ip: Optional[str] = None) -> Dict[str, Any]:
    if outcome not in OUTCOME_USEFULNESS:
        raise CaseError("That outcome is not recognised.")
    previous = serialise_case(row)
    row.outcome = outcome
    row.outcome_note = note
    row.outcome_recorded_at = utcnow()
    row.outcome_recorded_by_id = actor.id
    if row.status not in ("CLOSED", "RESOLVED"):
        session.add(CaseStatusHistory(case_id=row.id, from_status=row.status,
                                      to_status="RESOLVED", note=note, changed_by_id=actor.id))
        row.status = "RESOLVED"
    usefulness = OUTCOME_USEFULNESS[outcome]
    for signal in session.scalars(select(RiskSignal).where(
            RiskSignal.work_id == row.work_pk)).all():
        signal.usefulness = usefulness
    audit.record(session, "CASE_OUTCOME_RECORDED", actor, "case", row.case_ref, previous,
                 {"outcome": outcome, "signal_usefulness": usefulness}, ip)
    session.commit()
    return {**serialise_case(row), "calibration_note": CALIBRATION_NOTE}


def add_note(session: Session, actor, row: VerificationCase, body: str,
             ip: Optional[str] = None) -> Dict[str, Any]:
    note = CaseNote(case_id=row.id, author_id=actor.id, body=body)
    session.add(note)
    audit.record(session, "CASE_NOTE_ADDED", actor, "case", row.case_ref, None,
                 {"length": len(body)}, ip)
    session.commit()
    return {"id": note.id, "body": note.body, "author": actor.full_name,
            "created_at": note.created_at.isoformat()}


def update_checklist(session: Session, actor, row: VerificationCase,
                     checklist: List[Dict[str, Any]], ip: Optional[str] = None) -> Dict[str, Any]:
    previous = row.checklist
    row.checklist = checklist
    audit.record(session, "CHECKLIST_UPDATED", actor, "case", row.case_ref, previous,
                 checklist, ip)
    session.commit()
    return serialise_case(row)


def case_timeline(session: Session, row: VerificationCase) -> List[Dict[str, Any]]:
    events = [{"at": item.created_at.isoformat(), "type": "status",
               "title": f"Status changed to {item.to_status.replace('_', ' ')}",
               "actor": item.changed_by.full_name if item.changed_by else None,
               "body": item.note} for item in row.history]
    events += [{"at": item.created_at.isoformat(), "type": "note", "title": "Note added",
                "actor": item.author.full_name if item.author else None, "body": item.body}
               for item in row.notes]
    events += [{"at": item.created_at.isoformat(), "type": "assignment",
                "title": f"Assigned to {item.assigned_to.full_name}" if item.assigned_to
                         else "Assignment updated",
                "actor": item.assigned_by.full_name if item.assigned_by else None,
                "body": item.note} for item in row.assignments]
    events += [{"at": item.created_at.isoformat(), "type": "evidence",
                "title": f"Evidence uploaded: {item.original_filename}",
                "actor": item.uploaded_by.full_name if item.uploaded_by else None,
                "body": f"SHA-256 {item.checksum_sha256[:16]}..."} for item in row.evidence]
    return sorted(events, key=lambda item: item["at"])


# ---------------------------------------------------------------- analytics
def _scoped_works(principal):
    return apply_scope(select(Work, RiskScore).outerjoin(RiskScore,
                                                         RiskScore.work_id == Work.id), principal)


def summary(session: Session, principal) -> Dict[str, Any]:
    rows = session.execute(_scoped_works(principal)).all()
    scored = [score for _, score in rows if score]
    bands: Dict[str, int] = {}
    priorities: Dict[str, int] = {}
    for score in scored:
        bands[score.risk_band] = bands.get(score.risk_band, 0) + 1
        priorities[score.priority] = priorities.get(score.priority, 0) + 1
    sanctioned = sum(work.sanction_amount or 0 for work, _ in rows)
    spent = sum(work.expenditure or 0 for work, _ in rows)
    open_cases = session.scalar(select(func.count()).select_from(VerificationCase).where(
        VerificationCase.status.notin_(("CLOSED", "RESOLVED")))) or 0
    dataset_quality = session.scalars(select(DataQualityResult).where(
        DataQualityResult.scope == "DATASET").order_by(desc(DataQualityResult.id))).first()
    from .repositories import priority_queue
    return {"total_works": len(rows), "analysed_works": len(scored), "risk_bands": bands,
            "priorities": priorities, "total_sanctioned": sanctioned,
            "total_expenditure": spent,
            "utilisation_pct": round(100 * spent / sanctioned, 1) if sanctioned else None,
            "open_cases": int(open_cases),
            "data_quality_score": dataset_quality.score if dataset_quality else None,
            "last_analysed_at": max([score.analysed_at for score in scored],
                                    default=None).isoformat() if scored else None,
            "top_priority": priority_queue(session, principal, 10),
            "transparency_note": risk.TRANSPARENCY_NOTE}


def risk_distribution(session: Session, principal) -> Dict[str, Any]:
    counts: Dict[tuple, int] = {}
    for _, score in session.execute(_scoped_works(principal)).all():
        if score:
            key = (score.priority, score.risk_band)
            counts[key] = counts.get(key, 0) + 1
    return {"distribution": [{"priority": priority, "risk_band": band, "count": count}
                             for (priority, band), count in sorted(counts.items())]}


def trends(session: Session, principal) -> Dict[str, Any]:
    buckets: Dict[str, Dict[str, Any]] = {}
    stmt = apply_scope(select(Work.sanction_date, Work.sanction_amount, RiskScore.risk_band)
                       .outerjoin(RiskScore, RiskScore.work_id == Work.id), principal)
    for sanction_date, amount, band in session.execute(stmt).all():
        if sanction_date is None:
            continue
        key = sanction_date.strftime("%Y-%m")
        bucket = buckets.setdefault(key, {"month": key, "works": 0, "sanctioned": 0.0,
                                          "high_risk": 0})
        bucket["works"] += 1
        bucket["sanctioned"] += amount or 0
        if band == "HIGH":
            bucket["high_risk"] += 1
    return {"trends": [buckets[key] for key in sorted(buckets)]}


def category_breakdown(session: Session, principal) -> Dict[str, Any]:
    rows: Dict[str, Dict[str, Any]] = {}
    for work, score in session.execute(_scoped_works(principal)).all():
        key = work.category or risk.NO_DATA
        bucket = rows.setdefault(key, {"category": key, "works": 0, "sanctioned": 0.0,
                                       "high_risk": 0, "avg_risk": 0.0, "_sum": 0.0,
                                       "_scored": 0})
        bucket["works"] += 1
        bucket["sanctioned"] += work.sanction_amount or 0
        if score:
            bucket["_sum"] += score.risk_score
            bucket["_scored"] += 1
            if score.risk_band == "HIGH":
                bucket["high_risk"] += 1
    output = []
    for bucket in rows.values():
        scored = bucket.pop("_scored")
        total = bucket.pop("_sum")
        bucket["avg_risk"] = round(total / scored, 2) if scored else None
        output.append(bucket)
    return {"categories": sorted(output, key=lambda item: item["works"], reverse=True)}


def geography(session: Session, principal) -> Dict[str, Any]:
    stmt = apply_scope(
        select(Work.state, Work.district, func.count(Work.id),
               func.sum(case((RiskScore.risk_band == "HIGH", 1), else_=0)))
        .outerjoin(RiskScore, RiskScore.work_id == Work.id)
        .group_by(Work.state, Work.district), principal)
    rows = [{"state": state, "district": district, "works": int(total or 0),
             "high_risk": int(high or 0)}
            for state, district, total, high in session.execute(stmt).all()]
    has_geo = session.scalar(select(func.count()).select_from(Work)
                             .where(Work.latitude.isnot(None))) or 0
    return {"rows": sorted(rows, key=lambda item: item["high_risk"], reverse=True),
            "map_available": bool(has_geo),
            "map_note": None if has_geo else "Location data unavailable in the current dataset"}


def outcome_metrics(session: Session, principal) -> Dict[str, Any]:
    cases = session.scalars(select(VerificationCase)).all()
    reviewed = [row for row in cases if row.outcome]
    useful = [row for row in reviewed if OUTCOME_USEFULNESS[row.outcome] == "CONFIRMED_USEFUL"]
    false_positive = [row for row in reviewed if OUTCOME_USEFULNESS[row.outcome] == "NOT_USEFUL"]
    closed = [row for row in cases if row.status in ("CLOSED", "RESOLVED")]
    durations = [(row.first_reviewed_at - row.created_at).total_seconds() / 3600
                 for row in cases if row.first_reviewed_at and row.created_at]
    by_rule: Dict[str, Dict[str, int]] = {}
    for row in reviewed:
        for rule_id in row.signal_rule_ids or []:
            bucket = by_rule.setdefault(rule_id, {"rule_id": rule_id, "reviewed": 0, "useful": 0})
            bucket["reviewed"] += 1
            if OUTCOME_USEFULNESS[row.outcome] == "CONFIRMED_USEFUL":
                bucket["useful"] += 1
    return {"cases_total": len(cases), "cases_reviewed": len(reviewed),
            "alert_precision": round(100 * len(useful) / len(reviewed), 1) if reviewed else None,
            "false_positive_rate": (round(100 * len(false_positive) / len(reviewed), 1)
                                    if reviewed else None),
            "closure_rate": round(100 * len(closed) / len(cases), 1) if cases else None,
            "avg_hours_to_first_review": (round(sum(durations) / len(durations), 1)
                                          if durations else None),
            "backlog": len([row for row in cases
                            if row.status not in ("CLOSED", "RESOLVED")]),
            "signal_usefulness": sorted(by_rule.values(), key=lambda item: item["reviewed"],
                                        reverse=True),
            "calibration_note": CALIBRATION_NOTE}


def case_load(session: Session, principal) -> Dict[str, Any]:
    stmt = (select(User.full_name, User.role, func.count(VerificationCase.id),
                   func.sum(case((VerificationCase.status.notin_(("CLOSED", "RESOLVED")), 1),
                                 else_=0)))
            .join(VerificationCase, VerificationCase.assigned_to_id == User.id)
            .group_by(User.full_name, User.role))
    return {"rows": [{"officer": name, "role": role, "cases": int(total or 0),
                      "open_cases": int(open_count or 0)}
                     for name, role, total, open_count in session.execute(stmt).all()]}


def quality_overview(session: Session, principal) -> Dict[str, Any]:
    dataset_row = session.scalars(select(DataQualityResult).where(
        DataQualityResult.scope == "DATASET").order_by(desc(DataQualityResult.id))).first()
    worst = session.execute(
        select(Work.work_id, Work.description, DataQualityResult.score,
               DataQualityResult.missing_fields, DataQualityResult.issues)
        .join(DataQualityResult, DataQualityResult.work_id == Work.id)
        .where(DataQualityResult.scope == "RECORD")
        .order_by(DataQualityResult.score).limit(20)).all()
    dataset = session.scalars(select(Dataset).order_by(desc(Dataset.id))).first()
    return {"dataset": ({"score": dataset_row.score, "dimensions": dataset_row.dimensions,
                        "missing_fields": dataset_row.missing_fields}
                       if dataset_row else None),
            "worst_records": [{"work_id": work_id, "description": description, "score": score,
                               "missing_fields": missing, "issues": issues}
                              for work_id, description, score, missing, issues in worst],
            "latest_upload": ({"filename": dataset.filename, "status": dataset.status,
                               "records_received": dataset.records_received,
                               "records_accepted": dataset.records_accepted,
                               "records_rejected": dataset.records_rejected,
                               "warnings": dataset.warnings,
                               "field_availability": dataset.field_availability,
                               "is_prototype": dataset.is_prototype} if dataset else None),
            "note": risk.QUALITY_NOTE}


def notifications(session: Session, principal, unread_only: bool = False) -> Dict[str, Any]:
    stmt = select(Notification).where(Notification.user_id == principal.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    rows = session.scalars(stmt.order_by(desc(Notification.created_at)).limit(100)).all()
    return {"notifications": [{"id": row.id, "severity": row.severity, "title": row.title,
                               "body": row.body, "entity_type": row.entity_type,
                               "entity_ref": row.entity_ref, "is_read": row.is_read,
                               "created_at": row.created_at.isoformat()} for row in rows]}
