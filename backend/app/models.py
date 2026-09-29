"""Relational model. Risk results, cases, evidence and audit logs are all persisted."""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer,
                        String, Text, UniqueConstraint)
from sqlalchemy.orm import relationship
from .db import Base

ROLES = ("ADMIN", "MINISTRY", "STATE", "DISTRICT", "REVIEWER", "AUDITOR")
CASE_STATUSES = ("OPEN", "ASSIGNED", "UNDER_REVIEW", "FIELD_VERIFICATION", "ESCALATED",
                 "RESOLVED", "CLOSED")
STATUS_TRANSITIONS = {
    "OPEN": {"ASSIGNED", "UNDER_REVIEW", "ESCALATED", "CLOSED"},
    "ASSIGNED": {"UNDER_REVIEW", "FIELD_VERIFICATION", "ESCALATED", "OPEN", "CLOSED"},
    "UNDER_REVIEW": {"FIELD_VERIFICATION", "ESCALATED", "RESOLVED", "CLOSED"},
    "FIELD_VERIFICATION": {"UNDER_REVIEW", "ESCALATED", "RESOLVED", "CLOSED"},
    "ESCALATED": {"UNDER_REVIEW", "RESOLVED", "CLOSED"},
    "RESOLVED": {"CLOSED", "UNDER_REVIEW"},
    "CLOSED": set(),
}
CASE_OUTCOMES = ("VALID_ANOMALY", "FALSE_POSITIVE", "NEEDS_FIELD_VERIFICATION", "ESCALATED",
                 "NO_ISSUE_FOUND", "DATA_ISSUE")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    full_name = Column(String(160), nullable=False)
    role = Column(String(20), nullable=False)
    password_hash = Column(String(255), nullable=False)
    state = Column(String(120))
    district = Column(String(120))
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    source_label = Column(String(255))
    status = Column(String(20), default="UPLOADED", nullable=False)
    is_prototype = Column(Boolean, default=False, nullable=False)
    size_bytes = Column(Integer, default=0)
    columns = Column(JSON)
    records_received = Column(Integer, default=0)
    records_accepted = Column(Integer, default=0)
    records_rejected = Column(Integer, default=0)
    warnings = Column(JSON)
    rejected_records = Column(JSON)
    column_profiles = Column(JSON)
    field_availability = Column(JSON)
    processing_seconds = Column(Float)
    error = Column(Text)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class FieldMapping(Base):
    __tablename__ = "field_mappings"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    canonical_field = Column(String(60), nullable=False)
    source_column = Column(String(200))
    status = Column(String(20), nullable=False)
    note = Column(Text)


class Work(Base):
    __tablename__ = "works"
    id = Column(Integer, primary_key=True)
    work_id = Column(String(80), unique=True, nullable=False, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    description = Column(Text)
    state = Column(String(120), index=True)
    district = Column(String(120), index=True)
    constituency = Column(String(160))
    category = Column(String(120), index=True)
    agency = Column(String(200))
    sanction_amount = Column(Float)
    expenditure = Column(Float)
    progress_percent = Column(Float)
    sanction_date = Column(Date)
    expected_completion = Column(Date)
    actual_completion = Column(Date)
    status = Column(String(80))
    latitude = Column(Float)
    longitude = Column(Float)
    source_row = Column(JSON)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    risk_score = relationship("RiskScore", back_populates="work", uselist=False,
                             cascade="all, delete-orphan")
    quality_result = relationship(
        "DataQualityResult", uselist=False, viewonly=True,
        primaryjoin="and_(Work.id == DataQualityResult.work_id, "
                    "DataQualityResult.scope == 'RECORD')")


Index("ix_works_state_district", Work.state, Work.district)


class RiskScore(Base):
    __tablename__ = "risk_scores"
    id = Column(Integer, primary_key=True)
    work_id = Column(Integer, ForeignKey("works.id"), unique=True, nullable=False)
    risk_score = Column(Float, nullable=False)
    risk_band = Column(String(10), nullable=False, index=True)
    confidence_score = Column(Float, nullable=False)
    confidence_factors = Column(JSON)
    confidence_notes = Column(JSON)
    interpretation = Column(Text)
    priority = Column(String(4), nullable=False, index=True)
    priority_label = Column(String(40))
    priority_index = Column(Float, nullable=False)
    priority_components = Column(JSON)
    priority_rationale = Column(JSON)
    category_scores = Column(JSON)
    recommended_actions = Column(JSON)
    factors = Column(JSON)
    features = Column(JSON)
    engine_version = Column(String(20))
    ontology_version = Column(String(20))
    weight_version = Column(String(20))
    rule_versions = Column(JSON)
    similarity_backend = Column(String(80))
    analysed_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    work = relationship("Work", back_populates="risk_score")


Index("ix_risk_priority_index", RiskScore.priority_index)


class RiskSignal(Base):
    __tablename__ = "risk_signals"
    id = Column(Integer, primary_key=True)
    work_id = Column(Integer, ForeignKey("works.id"), nullable=False, index=True)
    rule_id = Column(String(40), nullable=False, index=True)
    name = Column(String(200))
    category = Column(String(10))
    severity = Column(String(10))
    method = Column(String(160))
    strength = Column(Float)
    statement = Column(Text)
    source_fields = Column(JSON)
    evidence = Column(JSON)
    recommended_actions = Column(JSON)
    false_positive_notes = Column(Text)
    rule_version = Column(String(20))
    related_work_ref = Column(String(80))
    usefulness = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class RiskRule(Base):
    __tablename__ = "risk_rules"
    id = Column(Integer, primary_key=True)
    rule_id = Column(String(40), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    category = Column(String(10), nullable=False)
    severity = Column(String(10), nullable=False)
    description = Column(Text)
    method = Column(String(160))
    required_fields = Column(JSON)
    evidence_fields = Column(JSON)
    recommended_actions = Column(JSON)
    false_positive_notes = Column(Text)
    params = Column(JSON)
    weight = Column(Float, default=1.0)
    is_active = Column(Boolean, default=True, nullable=False)
    version = Column(String(20), default="1.0")
    modified_by_id = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RiskRuleVersion(Base):
    __tablename__ = "risk_rule_versions"
    id = Column(Integer, primary_key=True)
    rule_pk = Column(Integer, ForeignKey("risk_rules.id"), nullable=False)
    version = Column(String(20), nullable=False)
    payload = Column(JSON)
    change_note = Column(Text)
    changed_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class DataQualityResult(Base):
    __tablename__ = "data_quality_results"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    work_id = Column(Integer, ForeignKey("works.id"), index=True)
    scope = Column(String(10), nullable=False)
    score = Column(Float, nullable=False)
    dimensions = Column(JSON)
    missing_fields = Column(JSON)
    issues = Column(JSON)
    quality_version = Column(String(20))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class PeerGroup(Base):
    __tablename__ = "peer_groups"
    id = Column(Integer, primary_key=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"))
    group_key = Column(String(255), nullable=False, index=True)
    dimensions = Column(JSON)
    metric = Column(String(60))
    peer_count = Column(Integer)
    median_value = Column(Float)
    p25_value = Column(Float)
    p75_value = Column(Float)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(Integer, primary_key=True)
    component = Column(String(40), nullable=False)
    version = Column(String(20), nullable=False)
    methodology = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    __table_args__ = (UniqueConstraint("component", "version"),)


class VerificationCase(Base):
    __tablename__ = "verification_cases"
    id = Column(Integer, primary_key=True)
    case_ref = Column(String(30), unique=True, nullable=False, index=True)
    work_pk = Column(Integer, ForeignKey("works.id"), nullable=False, index=True)
    work_ref = Column(String(80), nullable=False, index=True)
    status = Column(String(24), default="OPEN", nullable=False, index=True)
    priority = Column(String(4), index=True)
    risk_score = Column(Float)
    confidence_score = Column(Float)
    categories = Column(JSON)
    signal_rule_ids = Column(JSON)
    recommended_actions = Column(JSON)
    checklist = Column(JSON)
    outcome = Column(String(30))
    outcome_note = Column(Text)
    outcome_recorded_at = Column(DateTime(timezone=True))
    outcome_recorded_by_id = Column(Integer, ForeignKey("users.id"))
    assigned_to_id = Column(Integer, ForeignKey("users.id"), index=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    due_date = Column(Date)
    first_reviewed_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    history = relationship("CaseStatusHistory", back_populates="case",
                           cascade="all, delete-orphan", order_by="CaseStatusHistory.created_at")
    assignments = relationship("CaseAssignment", back_populates="case",
                               cascade="all, delete-orphan")
    notes = relationship("CaseNote", back_populates="case", cascade="all, delete-orphan",
                         order_by="CaseNote.created_at")
    evidence = relationship("Evidence", back_populates="case")


class CaseStatusHistory(Base):
    __tablename__ = "case_status_history"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("verification_cases.id"), nullable=False)
    from_status = Column(String(24))
    to_status = Column(String(24), nullable=False)
    note = Column(Text)
    changed_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    case = relationship("VerificationCase", back_populates="history")
    changed_by = relationship("User")


class CaseAssignment(Base):
    __tablename__ = "case_assignments"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("verification_cases.id"), nullable=False)
    assigned_to_id = Column(Integer, ForeignKey("users.id"))
    assigned_by_id = Column(Integer, ForeignKey("users.id"))
    note = Column(Text)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    case = relationship("VerificationCase", back_populates="assignments")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    assigned_by = relationship("User", foreign_keys=[assigned_by_id])


class CaseNote(Base):
    __tablename__ = "case_notes"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("verification_cases.id"), nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"))
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    case = relationship("VerificationCase", back_populates="notes")
    author = relationship("User")


class Evidence(Base):
    __tablename__ = "evidence"
    id = Column(Integer, primary_key=True)
    work_pk = Column(Integer, ForeignKey("works.id"), index=True)
    case_id = Column(Integer, ForeignKey("verification_cases.id"), index=True)
    doc_type = Column(String(60))
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    content_type = Column(String(120))
    size_bytes = Column(Integer)
    checksum_sha256 = Column(String(64), nullable=False)
    authenticity_note = Column(Text)
    uploaded_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    case = relationship("VerificationCase", back_populates="evidence")
    uploaded_by = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    severity = Column(String(10), default="INFO", nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text)
    entity_type = Column(String(40))
    entity_ref = Column(String(80))
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    action = Column(String(40), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"))
    actor_email = Column(String(200))
    actor_role = Column(String(20))
    entity_type = Column(String(40), index=True)
    entity_ref = Column(String(120), index=True)
    previous_value = Column(JSON)
    new_value = Column(JSON)
    ip_address = Column(String(60))
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class SystemConfig(Base):
    __tablename__ = "system_config"
    id = Column(Integer, primary_key=True)
    key = Column(String(80), unique=True, nullable=False)
    value = Column(JSON)
    version = Column(String(20), default="1.0")
    description = Column(Text)
    updated_by_id = Column(Integer, ForeignKey("users.id"))
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
