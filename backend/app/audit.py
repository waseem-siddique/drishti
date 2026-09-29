"""Mandatory audit logging. Previous and new values are stored, secrets are redacted."""
from __future__ import annotations
from typing import Any, Dict, Optional
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from .models import AuditLog

ACTIONS = ("LOGIN", "LOGIN_FAILED", "LOGOUT", "DATASET_UPLOADED", "INGESTION_COMPLETED",
           "RISK_ANALYSIS", "CASE_CREATED", "CASE_ASSIGNED", "CASE_STATUS_CHANGED",
           "CASE_OUTCOME_RECORDED", "CASE_NOTE_ADDED", "CHECKLIST_UPDATED", "EVIDENCE_UPLOADED",
           "RULE_UPDATED", "CONFIG_UPDATED", "USER_CREATED", "USER_UPDATED")
_SENSITIVE = ("password", "token", "secret", "api_key", "authorization")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("[redacted]" if any(word in key.lower() for word in _SENSITIVE)
                      else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def record(session: Session, action: str, actor: Any, entity_type: Optional[str] = None,
           entity_ref: Optional[str] = None, previous_value: Any = None, new_value: Any = None,
           ip_address: Optional[str] = None, commit: bool = False) -> AuditLog:
    entry = AuditLog(action=action, actor_id=getattr(actor, "id", None),
                     actor_email=getattr(actor, "email", None),
                     actor_role=getattr(actor, "role", None), entity_type=entity_type,
                     entity_ref=entity_ref, previous_value=_redact(previous_value),
                     new_value=_redact(new_value), ip_address=ip_address)
    session.add(entry)
    if commit:
        session.commit()
    return entry


def serialise(entry: AuditLog) -> Dict[str, Any]:
    return {"id": entry.id, "action": entry.action, "actor_email": entry.actor_email,
            "actor_role": entry.actor_role, "entity_type": entry.entity_type,
            "entity_ref": entry.entity_ref, "previous_value": entry.previous_value,
            "new_value": entry.new_value, "ip_address": entry.ip_address,
            "created_at": entry.created_at.isoformat() if entry.created_at else None}


def query(session: Session, action: Optional[str] = None, entity_type: Optional[str] = None,
          entity_ref: Optional[str] = None, page: int = 1, page_size: int = 50) -> Dict[str, Any]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_ref:
        stmt = stmt.where(AuditLog.entity_ref == entity_ref)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    page_size = max(1, min(200, page_size))
    rows = session.scalars(stmt.order_by(desc(AuditLog.created_at))
                           .offset((max(1, page) - 1) * page_size).limit(page_size)).all()
    return {"items": [serialise(row) for row in rows], "total": int(total), "page": page,
            "page_size": page_size, "actions": list(ACTIONS)}
