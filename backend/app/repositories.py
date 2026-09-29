"""Data access for works. Filtering, sorting, scoping and pagination happen in SQL."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session
from .models import RiskScore, Work

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 200
SORTABLE = {"priority_index": RiskScore.priority_index, "risk_score": RiskScore.risk_score,
            "confidence_score": RiskScore.confidence_score, "work_id": Work.work_id,
            "sanction_amount": Work.sanction_amount, "expenditure": Work.expenditure,
            "progress_percent": Work.progress_percent, "sanction_date": Work.sanction_date,
            "district": Work.district, "category": Work.category}


@dataclass
class WorkFilters:
    search: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    category: Optional[str] = None
    agency: Optional[str] = None
    risk_band: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None


def apply_scope(stmt, principal) -> Any:
    scope = principal.scope
    if scope["mode"] == "STATE" and scope.get("state"):
        return stmt.where(Work.state == scope["state"])
    if scope["mode"] in ("DISTRICT", "ASSIGNED_OR_DISTRICT") and scope.get("district"):
        return stmt.where(Work.district == scope["district"])
    return stmt


def _apply_filters(stmt, filters: WorkFilters):
    if filters.search:
        pattern = f"%{filters.search.strip()}%"
        stmt = stmt.where(or_(Work.work_id.ilike(pattern), Work.description.ilike(pattern),
                              Work.agency.ilike(pattern)))
    for column, value in ((Work.state, filters.state), (Work.district, filters.district),
                          (Work.category, filters.category), (Work.agency, filters.agency),
                          (Work.status, filters.status),
                          (RiskScore.risk_band, filters.risk_band),
                          (RiskScore.priority, filters.priority)):
        if value:
            stmt = stmt.where(column == value)
    return stmt


def serialise_row(work: Work, score: Optional[RiskScore]) -> Dict[str, Any]:
    return {
        "work_id": work.work_id, "description": work.description, "state": work.state,
        "district": work.district, "constituency": work.constituency,
        "category": work.category, "agency": work.agency,
        "sanction_amount": work.sanction_amount, "expenditure": work.expenditure,
        "progress_percent": work.progress_percent,
        "sanction_date": work.sanction_date.isoformat() if work.sanction_date else None,
        "expected_completion": (work.expected_completion.isoformat()
                                if work.expected_completion else None),
        "actual_completion": (work.actual_completion.isoformat()
                              if work.actual_completion else None),
        "status": work.status, "latitude": work.latitude, "longitude": work.longitude,
        "risk_score": score.risk_score if score else None,
        "risk_band": score.risk_band if score else None,
        "confidence_score": score.confidence_score if score else None,
        "priority": score.priority if score else None,
        "priority_label": score.priority_label if score else None,
        "priority_index": score.priority_index if score else None,
        "signal_count": len(score.factors or []) if score else 0,
        "analysed_at": score.analysed_at.isoformat() if score and score.analysed_at else None,
    }


def list_works(session: Session, principal, filters: WorkFilters, page: int = 1,
               page_size: int = DEFAULT_PAGE_SIZE, sort: str = "priority_index",
               direction: str = "desc") -> Dict[str, Any]:
    page = max(1, page)
    page_size = max(1, min(MAX_PAGE_SIZE, page_size))
    stmt = _apply_filters(apply_scope(select(Work, RiskScore).outerjoin(
        RiskScore, RiskScore.work_id == Work.id), principal), filters)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    column = SORTABLE.get(sort, RiskScore.priority_index)
    order = asc(column) if direction == "asc" else desc(column)
    rows = session.execute(stmt.order_by(order, Work.work_id)
                           .offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [serialise_row(work, score) for work, score in rows], "total": int(total),
            "page": page, "page_size": page_size, "sort": sort, "direction": direction,
            "pages": max(1, (int(total) + page_size - 1) // page_size),
            "sortable": sorted(SORTABLE)}


def get_work(session: Session, principal, work_ref: str):
    stmt = apply_scope(select(Work).where(Work.work_id == work_ref), principal)
    return session.scalar(stmt)


def priority_queue(session: Session, principal, limit: int = 10) -> List[Dict[str, Any]]:
    stmt = apply_scope(select(Work, RiskScore).join(RiskScore, RiskScore.work_id == Work.id),
                       principal).order_by(desc(RiskScore.priority_index)).limit(limit)
    return [serialise_row(work, score) for work, score in session.execute(stmt).all()]


def filter_options(session: Session, principal) -> Dict[str, List[str]]:
    options: Dict[str, List[str]] = {}
    for name, column in (("state", Work.state), ("district", Work.district),
                         ("category", Work.category), ("agency", Work.agency),
                         ("status", Work.status)):
        stmt = apply_scope(select(column).where(column.isnot(None)).distinct(), principal)
        options[name] = sorted({value for (value,) in session.execute(stmt).all() if value})
    options["risk_band"] = ["HIGH", "MEDIUM", "LOW"]
    options["priority"] = ["P1", "P2", "P3"]
    return options
