"""HTTP layer. Every number returned here comes from the database or the engine."""
from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session
from . import audit, integrations, llm, repositories, services
from . import risk as risk_engine
from .config import get_settings
from .db import get_session
from .deps import Principal, find_user_by_email, get_current_user, require
from .ingestion import IngestionError, run_ingestion
from .models import (Dataset, Evidence, FieldMapping, Notification, ROLES, RiskRule, RiskSignal,
                     SystemConfig, User, VerificationCase, Work)
from .schemas import (CaseAssignRequest, CaseCreateRequest, CaseNoteRequest, CaseOutcomeRequest,
                      CaseStatusRequest, ChecklistUpdateRequest, ConfigUpdateRequest,
                      ExplainRequest, LoginRequest, RuleUpdateRequest, UserCreateRequest,
                      UserUpdateRequest)
from .security import (ROLE_LABELS, create_token, file_checksum, hash_password, permissions_for,
                       safe_filename, verify_password)

ALLOWED_EVIDENCE_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".csv", ".xlsx", ".docx", ".txt")

auth_router = APIRouter(tags=["auth"])
works_router = APIRouter(tags=["works"])
cases_router = APIRouter(prefix="/cases", tags=["cases"])
insights_router = APIRouter(tags=["insights"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _load_work(session: Session, principal: Principal, work_ref: str) -> Work:
    work = repositories.get_work(session, principal, work_ref)
    if work is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"Work {work_ref} was not found in your scope.")
    return work


def _load_case(session: Session, principal: Principal, case_ref: str) -> VerificationCase:
    row = session.scalar(select(VerificationCase).where(VerificationCase.case_ref == case_ref))
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Case {case_ref} was not found.")
    scope = principal.scope
    if scope["mode"] == "ASSIGNED_OR_DISTRICT" and row.assigned_to_id != principal.id:
        work = session.get(Work, row.work_pk)
        if work is None or work.district != scope.get("district"):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "This case is outside the work assigned to you.")
    return row


def _store_evidence(session: Session, principal: Principal, upload: UploadFile, content: bytes,
                    doc_type: Optional[str], work: Optional[Work],
                    case: Optional[VerificationCase], ip: Optional[str]) -> Dict[str, Any]:
    settings = get_settings()
    if not (upload.filename or "").lower().endswith(ALLOWED_EVIDENCE_SUFFIXES):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That file type cannot be attached as evidence.")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Evidence files must be under {settings.max_upload_mb} MB.")
    directory = Path(settings.evidence_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stored = safe_filename(upload.filename or "evidence")
    (directory / stored).write_bytes(content)
    row = Evidence(work_pk=work.id if work else (case.work_pk if case else None),
                   case_id=case.id if case else None, doc_type=doc_type,
                   original_filename=upload.filename or stored, stored_filename=stored,
                   content_type=upload.content_type, size_bytes=len(content),
                   checksum_sha256=file_checksum(content),
                   authenticity_note=services.AUTHENTICITY_NOTE, uploaded_by_id=principal.id)
    session.add(row)
    audit.record(session, "EVIDENCE_UPLOADED", principal, "evidence",
                 case.case_ref if case else (work.work_id if work else None), None,
                 {"filename": row.original_filename, "checksum": row.checksum_sha256}, ip)
    session.commit()
    return services.serialise_evidence(row)


# ---------------------------------------------------------------- auth
@auth_router.post("/auth/login")
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_session)):
    settings = get_settings()
    user = find_user_by_email(session, payload.email)
    if user is None or not user.is_active or not verify_password(payload.password,
                                                                 user.password_hash):
        audit.record(session, "LOGIN_FAILED", None, "user", payload.email, None,
                     {"email": payload.email}, _client_ip(request), commit=True)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That email or password is incorrect.")
    user.last_login_at = services.utcnow()
    token = create_token({"sub": str(user.id), "role": user.role}, settings.jwt_secret,
                         settings.session_minutes)
    audit.record(session, "LOGIN", user, "user", user.email, None, {"role": user.role},
                 _client_ip(request), commit=True)
    return {"token": token, "expires_in_minutes": settings.session_minutes,
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name,
                     "role": user.role, "role_label": ROLE_LABELS.get(user.role, user.role),
                     "state": user.state, "district": user.district,
                     "permissions": sorted(permissions_for(user.role))}}


@auth_router.post("/auth/logout")
def logout(request: Request, current: Principal = Depends(get_current_user),
           session: Session = Depends(get_session)):
    audit.record(session, "LOGOUT", current, "user", current.email, None, None,
                 _client_ip(request), commit=True)
    return {"detail": "Signed out."}


@auth_router.get("/me")
def me(current: Principal = Depends(get_current_user)):
    return current.to_dict()


# ---------------------------------------------------------------- works
@works_router.get("/works")
def list_works(current: Principal = Depends(require("works:read")),
               session: Session = Depends(get_session), search: Optional[str] = None,
               state: Optional[str] = None, district: Optional[str] = None,
               category: Optional[str] = None, agency: Optional[str] = None,
               risk_band: Optional[str] = None, priority: Optional[str] = None,
               work_status: Optional[str] = None, page: int = 1,
               page_size: int = repositories.DEFAULT_PAGE_SIZE,
               sort: str = "priority_index", direction: str = "desc"):
    filters = repositories.WorkFilters(search, state, district, category, agency, risk_band,
                                       priority, work_status)
    return repositories.list_works(session, current, filters, page, page_size, sort, direction)


@works_router.get("/works/filters")
def work_filters(current: Principal = Depends(require("works:read")),
                 session: Session = Depends(get_session)):
    return repositories.filter_options(session, current)


@works_router.get("/works/{work_ref}")
def work_detail(work_ref: str, current: Principal = Depends(require("works:read")),
                session: Session = Depends(get_session)):
    return services.dossier(session, _load_work(session, current, work_ref))


@works_router.get("/works/{work_ref}/risk")
def work_risk(work_ref: str, current: Principal = Depends(require("risk:read")),
              session: Session = Depends(get_session)):
    payload = services.dossier(session, _load_work(session, current, work_ref))
    return {"work_id": payload["work_id"], "risk": payload["risk"], "factors": payload["factors"],
            "signals": payload["signals"], "peer_benchmark": payload["peer_benchmark"],
            "data_quality": payload["data_quality"],
            "transparency_note": risk_engine.TRANSPARENCY_NOTE}


@works_router.post("/works/{work_ref}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_work_evidence(work_ref: str, request: Request, file: UploadFile = File(...),
                               doc_type: Optional[str] = Form(default=None),
                               current: Principal = Depends(require("evidence:upload")),
                               session: Session = Depends(get_session)):
    work = _load_work(session, current, work_ref)
    return _store_evidence(session, current, file, await file.read(), doc_type, work, None,
                           _client_ip(request))


# ---------------------------------------------------------------- cases
@cases_router.get("")
def list_cases(current: Principal = Depends(require("cases:read")),
               session: Session = Depends(get_session), case_status: Optional[str] = None,
               assigned_to_me: bool = False, page: int = 1, page_size: int = 25):
    stmt = select(VerificationCase)
    if case_status:
        stmt = stmt.where(VerificationCase.status == case_status)
    if assigned_to_me or current.scope["mode"] == "ASSIGNED_OR_DISTRICT":
        stmt = stmt.where(VerificationCase.assigned_to_id == current.id)
    rows = session.scalars(stmt.order_by(desc(VerificationCase.updated_at))
                           .offset((max(1, page) - 1) * page_size).limit(page_size)).all()
    return {"items": [services.serialise_case(row) for row in rows], "page": page,
            "page_size": page_size}


@cases_router.post("", status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreateRequest, request: Request,
                current: Principal = Depends(require("cases:create")),
                session: Session = Depends(get_session)):
    work = _load_work(session, current, payload.work_ref)
    try:
        return services.create_case(session, current, work, payload.note, payload.assign_to_id,
                                    _client_ip(request))
    except services.CaseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@cases_router.get("/{case_ref}")
def case_detail(case_ref: str, current: Principal = Depends(require("cases:read")),
                session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    work = session.get(Work, row.work_pk)
    return {"case": services.serialise_case(row),
            "timeline": services.case_timeline(session, row),
            "dossier": services.dossier(session, work) if work else None,
            "evidence": [services.serialise_evidence(item) for item in row.evidence],
            "outcomes": list(services.OUTCOME_USEFULNESS)}


@cases_router.patch("/{case_ref}/status")
def change_case_status(case_ref: str, payload: CaseStatusRequest, request: Request,
                       current: Principal = Depends(require("cases:update")),
                       session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    try:
        return services.change_status(session, current, row, payload.status, payload.note,
                                      _client_ip(request))
    except services.CaseError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@cases_router.post("/{case_ref}/assign")
def assign_case(case_ref: str, payload: CaseAssignRequest, request: Request,
                current: Principal = Depends(require("cases:assign")),
                session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    try:
        return services.assign_case(session, current, row, payload.assign_to_id, payload.note,
                                    _client_ip(request))
    except services.CaseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@cases_router.post("/{case_ref}/outcome")
def record_outcome(case_ref: str, payload: CaseOutcomeRequest, request: Request,
                   current: Principal = Depends(require("cases:outcome")),
                   session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    try:
        return services.record_outcome(session, current, row, payload.outcome, payload.note,
                                       _client_ip(request))
    except services.CaseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@cases_router.post("/{case_ref}/notes", status_code=status.HTTP_201_CREATED)
def add_case_note(case_ref: str, payload: CaseNoteRequest, request: Request,
                  current: Principal = Depends(require("cases:update")),
                  session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    return services.add_note(session, current, row, payload.body, _client_ip(request))


@cases_router.patch("/{case_ref}/checklist")
def update_checklist(case_ref: str, payload: ChecklistUpdateRequest, request: Request,
                     current: Principal = Depends(require("cases:update")),
                     session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    return services.update_checklist(session, current, row, payload.checklist,
                                     _client_ip(request))


@cases_router.post("/{case_ref}/evidence", status_code=status.HTTP_201_CREATED)
async def upload_case_evidence(case_ref: str, request: Request, file: UploadFile = File(...),
                               doc_type: Optional[str] = Form(default=None),
                               current: Principal = Depends(require("evidence:upload")),
                               session: Session = Depends(get_session)):
    row = _load_case(session, current, case_ref)
    return _store_evidence(session, current, file, await file.read(), doc_type, None, row,
                           _client_ip(request))


# ---------------------------------------------------------------- insights
@insights_router.get("/verification/workspace")
def workspace(current: Principal = Depends(require("cases:read")),
              session: Session = Depends(get_session), case_ref: Optional[str] = None):
    queue = session.scalars(select(VerificationCase).where(
        VerificationCase.status.notin_(("CLOSED", "RESOLVED")))
        .order_by(VerificationCase.priority, desc(VerificationCase.risk_score)).limit(50)).all()
    if current.scope["mode"] == "ASSIGNED_OR_DISTRICT":
        queue = [row for row in queue if row.assigned_to_id == current.id]
    selected = None
    ref = case_ref or (queue[0].case_ref if queue else None)
    if ref:
        row = _load_case(session, current, ref)
        work = session.get(Work, row.work_pk)
        selected = {"case": services.serialise_case(row),
                    "timeline": services.case_timeline(session, row),
                    "dossier": services.dossier(session, work) if work else None}
    return {"queue": [services.serialise_case(row) for row in queue], "selected": selected,
            "outcomes": list(services.OUTCOME_USEFULNESS)}


@insights_router.get("/dashboard/summary")
def dashboard_summary(current: Principal = Depends(require("analytics:read")),
                      session: Session = Depends(get_session)):
    return services.summary(session, current)


@insights_router.get("/dashboard/risk-distribution")
def dashboard_distribution(current: Principal = Depends(require("analytics:read")),
                           session: Session = Depends(get_session)):
    return services.risk_distribution(session, current)


@insights_router.get("/dashboard/trends")
def dashboard_trends(current: Principal = Depends(require("analytics:read")),
                     session: Session = Depends(get_session)):
    return services.trends(session, current)


@insights_router.get("/analytics/categories")
def analytics_categories(current: Principal = Depends(require("analytics:read")),
                         session: Session = Depends(get_session)):
    return services.category_breakdown(session, current)


@insights_router.get("/analytics/geography")
def analytics_geography(current: Principal = Depends(require("analytics:read")),
                        session: Session = Depends(get_session)):
    return services.geography(session, current)


@insights_router.get("/analytics/outcomes")
def analytics_outcomes(current: Principal = Depends(require("analytics:read")),
                       session: Session = Depends(get_session)):
    return services.outcome_metrics(session, current)


@insights_router.get("/analytics/case-load")
def analytics_case_load(current: Principal = Depends(require("analytics:read")),
                        session: Session = Depends(get_session)):
    return services.case_load(session, current)


@insights_router.get("/data-quality")
def data_quality(current: Principal = Depends(require("quality:read")),
                 session: Session = Depends(get_session)):
    return services.quality_overview(session, current)


@insights_router.get("/risk/rules")
def risk_rules(current: Principal = Depends(require("risk:read")),
               session: Session = Depends(get_session)):
    rows = session.scalars(select(RiskRule).order_by(RiskRule.rule_id)).all()
    config = services.weight_config(session)
    return {"rules": [services.serialise_rule(row) for row in rows],
            "weights": config.value if config else {},
            "weight_version": config.version if config else None,
            "ontology_version": risk_engine.ONTOLOGY_VERSION,
            "engine_version": risk_engine.ENGINE_VERSION,
            "categories": risk_engine.CATEGORIES}


@insights_router.get("/risk/signals")
def risk_signals(current: Principal = Depends(require("risk:read")),
                 session: Session = Depends(get_session), rule_id: Optional[str] = None,
                 limit: int = 100):
    stmt = select(RiskSignal, Work).join(Work, Work.id == RiskSignal.work_id)
    stmt = repositories.apply_scope(stmt, current)
    if rule_id:
        stmt = stmt.where(RiskSignal.rule_id == rule_id)
    rows = session.execute(stmt.order_by(desc(RiskSignal.strength)).limit(limit)).all()
    return {"signals": [{"rule_id": signal.rule_id, "name": signal.name,
                         "work_id": work.work_id, "district": work.district,
                         "severity": signal.severity, "strength": signal.strength,
                         "statement": signal.statement, "usefulness": signal.usefulness}
                        for signal, work in rows]}


@insights_router.post("/risk/analyze")
def run_analysis(request: Request, current: Principal = Depends(require("risk:analyse")),
                 session: Session = Depends(get_session)):
    try:
        return services.analyse_dataset(session, current, _client_ip(request))
    except services.CaseError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@insights_router.post("/risk/explain")
def explain(payload: ExplainRequest, current: Principal = Depends(require("risk:read")),
            session: Session = Depends(get_session)):
    work = _load_work(session, current, payload.work_ref)
    return llm.explain(services.dossier(session, work))


@insights_router.post("/ingestion/upload", status_code=status.HTTP_201_CREATED)
async def upload_dataset(request: Request, file: UploadFile = File(...),
                         current: Principal = Depends(require("ingestion:upload")),
                         session: Session = Depends(get_session)):
    settings = get_settings()
    started = time.perf_counter()
    content = await file.read()
    dataset = Dataset(filename=file.filename or "upload", status="VALIDATING",
                      size_bytes=len(content), uploaded_by_id=current.id)
    session.add(dataset)
    session.commit()
    try:
        result = run_ingestion(content, file.filename or "upload", settings.max_upload_mb)
    except IngestionError as exc:
        dataset.status = "FAILED"
        dataset.error = str(exc)
        audit.record(session, "DATASET_UPLOADED", current, "dataset", str(dataset.id), None,
                     {"status": "FAILED", "error": str(exc)}, _client_ip(request), commit=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    report = result.report()
    dataset.status = "PROCESSING"
    dataset.columns = report["columns"]
    dataset.records_received = report["records_received"]
    dataset.records_accepted = report["records_accepted"]
    dataset.records_rejected = report["records_rejected"]
    dataset.warnings = report["warnings"]
    dataset.rejected_records = report["rejected_records"]
    dataset.column_profiles = report["column_profiles"]
    dataset.field_availability = report["field_availability"]
    for field_name, spec in report["mapping"].items():
        session.add(FieldMapping(dataset_id=dataset.id, canonical_field=field_name,
                                 source_column=spec["source_column"], status=spec["status"],
                                 note=spec["note"]))
    for row in result.rows:
        work = session.scalar(select(Work).where(Work.work_id == row["work_id"])) or Work(
            work_id=row["work_id"])
        work.dataset_id = dataset.id
        work.description = row.get("description")
        work.state = row.get("state")
        work.district = row.get("district")
        work.constituency = row.get("constituency")
        work.category = row.get("category")
        work.agency = row.get("agency")
        work.sanction_amount = risk_engine.parse_number(row.get("sanction_amount"))
        work.expenditure = risk_engine.parse_number(row.get("expenditure"))
        work.progress_percent = risk_engine.parse_number(row.get("progress_percent"))
        work.sanction_date = risk_engine.parse_date(row.get("sanction_date"))
        work.expected_completion = risk_engine.parse_date(row.get("expected_completion"))
        work.actual_completion = risk_engine.parse_date(row.get("actual_completion"))
        work.status = row.get("status")
        work.latitude = risk_engine.parse_number(row.get("latitude"))
        work.longitude = risk_engine.parse_number(row.get("longitude"))
        work.source_row = row.get("raw")
        session.add(work)
    session.commit()
    analysis = services.analyse_dataset(session, current, _client_ip(request))
    dataset.status = "COMPLETED"
    dataset.processing_seconds = round(time.perf_counter() - started, 3)
    audit.record(session, "INGESTION_COMPLETED", current, "dataset", str(dataset.id), None,
                 {"accepted": dataset.records_accepted, "rejected": dataset.records_rejected},
                 _client_ip(request), commit=True)
    return {"dataset_id": dataset.id, "status": dataset.status,
            "processing_seconds": dataset.processing_seconds, "report": report,
            "analysis": analysis}


@insights_router.get("/ingestion/jobs")
def ingestion_jobs(current: Principal = Depends(require("quality:read")),
                   session: Session = Depends(get_session)):
    rows = session.scalars(select(Dataset).order_by(desc(Dataset.id)).limit(50)).all()
    return {"jobs": [{"id": row.id, "filename": row.filename, "status": row.status,
                      "records_received": row.records_received,
                      "records_accepted": row.records_accepted,
                      "records_rejected": row.records_rejected,
                      "processing_seconds": row.processing_seconds,
                      "is_prototype": row.is_prototype, "error": row.error,
                      "created_at": row.created_at.isoformat()} for row in rows]}


@insights_router.get("/ingestion/jobs/{job_id}")
def ingestion_job(job_id: int, current: Principal = Depends(require("quality:read")),
                  session: Session = Depends(get_session)):
    row = session.get(Dataset, job_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That ingestion job was not found.")
    mappings = session.scalars(select(FieldMapping).where(
        FieldMapping.dataset_id == row.id)).all()
    return {"id": row.id, "filename": row.filename, "status": row.status,
            "columns": row.columns, "warnings": row.warnings,
            "rejected_records": row.rejected_records, "column_profiles": row.column_profiles,
            "field_availability": row.field_availability, "is_prototype": row.is_prototype,
            "mapping": [{"canonical_field": item.canonical_field,
                         "source_column": item.source_column, "status": item.status,
                         "note": item.note} for item in mappings]}


@insights_router.get("/notifications")
def list_notifications(current: Principal = Depends(require("notifications:read")),
                       session: Session = Depends(get_session), unread_only: bool = False):
    return services.notifications(session, current, unread_only)


@insights_router.patch("/notifications/{notification_id}/read")
def mark_notification(notification_id: int,
                      current: Principal = Depends(require("notifications:read")),
                      session: Session = Depends(get_session)):
    row = session.get(Notification, notification_id)
    if row is None or row.user_id != current.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That alert was not found.")
    row.is_read = True
    session.commit()
    return {"id": row.id, "is_read": True}


@insights_router.get("/search")
def global_search(q: str = Query(min_length=2), current: Principal = Depends(get_current_user),
                  session: Session = Depends(get_session)):
    pattern = f"%{q.strip()}%"
    work_stmt = repositories.apply_scope(select(Work).where(
        or_(Work.work_id.ilike(pattern), Work.description.ilike(pattern),
            Work.agency.ilike(pattern))).limit(8), current)
    cases = session.scalars(select(VerificationCase).where(
        or_(VerificationCase.case_ref.ilike(pattern),
            VerificationCase.work_ref.ilike(pattern))).limit(8)).all()
    return {"works": [{"work_id": work.work_id, "description": work.description,
                       "district": work.district}
                      for work in session.scalars(work_stmt).all()],
            "cases": [{"case_ref": row.case_ref, "work_id": row.work_ref, "status": row.status}
                      for row in cases]}


@insights_router.get("/integrations")
def integration_status(current: Principal = Depends(get_current_user)):
    return integrations.registry_status()


# ---------------------------------------------------------------- administration
@admin_router.get("/users")
def list_users(current: Principal = Depends(require("admin:users")),
               session: Session = Depends(get_session)):
    rows = session.scalars(select(User).order_by(User.full_name)).all()
    return {"users": [{"id": row.id, "email": row.email, "full_name": row.full_name,
                       "role": row.role, "role_label": ROLE_LABELS.get(row.role, row.role),
                       "state": row.state, "district": row.district,
                       "is_active": row.is_active,
                       "last_login_at": (row.last_login_at.isoformat()
                                         if row.last_login_at else None)} for row in rows],
            "roles": list(ROLES)}


@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, request: Request,
                current: Principal = Depends(require("admin:users")),
                session: Session = Depends(get_session)):
    if payload.role not in ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That role does not exist.")
    if find_user_by_email(session, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with that email already exists.")
    row = User(email=payload.email.lower(), full_name=payload.full_name, role=payload.role,
               password_hash=hash_password(payload.password), state=payload.state,
               district=payload.district)
    session.add(row)
    audit.record(session, "USER_CREATED", current, "user", payload.email, None,
                 {"role": payload.role}, _client_ip(request), commit=True)
    return {"id": row.id, "email": row.email, "role": row.role}


@admin_router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdateRequest, request: Request,
                current: Principal = Depends(require("admin:users")),
                session: Session = Depends(get_session)):
    row = session.get(User, user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That user was not found.")
    previous = {"role": row.role, "is_active": row.is_active, "state": row.state,
                "district": row.district}
    if payload.role:
        if payload.role not in ROLES:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "That role does not exist.")
        row.role = payload.role
    if payload.is_active is not None:
        row.is_active = payload.is_active
    if payload.state is not None:
        row.state = payload.state
    if payload.district is not None:
        row.district = payload.district
    audit.record(session, "USER_UPDATED", current, "user", row.email, previous,
                 {"role": row.role, "is_active": row.is_active}, _client_ip(request),
                 commit=True)
    return {"id": row.id, "email": row.email, "role": row.role, "is_active": row.is_active}


@admin_router.patch("/rules/{rule_id}")
def update_rule(rule_id: str, payload: RuleUpdateRequest, request: Request,
                current: Principal = Depends(require("admin:rules")),
                session: Session = Depends(get_session)):
    try:
        return services.update_rule(session, current, rule_id,
                                    payload.model_dump(exclude_none=True), _client_ip(request))
    except services.CaseError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@admin_router.get("/config")
def list_config(current: Principal = Depends(require("admin:config")),
                session: Session = Depends(get_session)):
    rows = session.scalars(select(SystemConfig)).all()
    return {"config": [{"key": row.key, "value": row.value, "version": row.version,
                        "description": row.description,
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None}
                       for row in rows]}


@admin_router.patch("/config/{key}")
def update_config(key: str, payload: ConfigUpdateRequest, request: Request,
                  current: Principal = Depends(require("admin:config")),
                  session: Session = Depends(get_session)):
    row = session.scalar(select(SystemConfig).where(SystemConfig.key == key))
    if row is None:
        row = SystemConfig(key=key, value=payload.value, description=payload.description)
        session.add(row)
        previous = None
    else:
        previous = row.value
        row.value = payload.value
        major, _, minor = (row.version or "1.0").partition(".")
        row.version = f"{major}.{int(minor or 0) + 1}"
    row.updated_by_id = current.id
    audit.record(session, "CONFIG_UPDATED", current, "config", key, previous, payload.value,
                 _client_ip(request), commit=True)
    return {"key": row.key, "value": row.value, "version": row.version}


@admin_router.get("/audit")
def audit_trail(current: Principal = Depends(require("audit:read")),
                session: Session = Depends(get_session), action: Optional[str] = None,
                entity_type: Optional[str] = None, entity_ref: Optional[str] = None,
                page: int = 1, page_size: int = 50):
    return audit.query(session, action, entity_type, entity_ref, page, page_size)


ROUTERS = (auth_router, works_router, cases_router, insights_router, admin_router)
