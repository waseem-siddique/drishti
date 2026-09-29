from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)


class CaseCreateRequest(BaseModel):
    work_ref: str
    note: Optional[str] = Field(default=None, max_length=4000)
    assign_to_id: Optional[int] = None


class CaseAssignRequest(BaseModel):
    assign_to_id: int
    note: Optional[str] = Field(default=None, max_length=2000)


class CaseStatusRequest(BaseModel):
    status: str
    note: Optional[str] = Field(default=None, max_length=2000)


class CaseOutcomeRequest(BaseModel):
    outcome: str
    note: Optional[str] = Field(default=None, max_length=4000)


class CaseNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class ChecklistUpdateRequest(BaseModel):
    checklist: List[Dict[str, Any]]


class RuleUpdateRequest(BaseModel):
    is_active: Optional[bool] = None
    weight: Optional[float] = Field(default=None, ge=0, le=3)
    params: Optional[Dict[str, float]] = None
    change_note: Optional[str] = Field(default=None, max_length=500)


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    role: str
    password: str = Field(min_length=8, max_length=200)
    state: Optional[str] = None
    district: Optional[str] = None


class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    state: Optional[str] = None
    district: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    value: Dict[str, Any]
    description: Optional[str] = None


class ExplainRequest(BaseModel):
    work_ref: str
