"""Authentication and authorisation dependencies. Every rule is enforced server side."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_session
from .models import User
from .security import ROLE_LABELS, TokenError, decode_token, has_permission, permissions_for, scope_for


@dataclass
class Principal:
    id: int
    email: str
    full_name: str
    role: str
    state: Optional[str]
    district: Optional[str]

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def scope(self) -> Dict[str, Any]:
        return scope_for(self.role, self.state, self.district)

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "email": self.email, "full_name": self.full_name,
                "role": self.role, "role_label": self.role_label, "state": self.state,
                "district": self.district, "scope": self.scope,
                "permissions": sorted(permissions_for(self.role))}


def find_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.scalar(select(User).where(User.email == email.lower().strip()))


def get_current_user(authorization: str = Header(default=""),
                     session: Session = Depends(get_session)) -> Principal:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in to continue.")
    try:
        claims = decode_token(authorization.split(" ", 1)[1].strip(), get_settings().jwt_secret)
    except TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    user = session.get(User, int(claims.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That account is no longer active.")
    return Principal(user.id, user.email, user.full_name, user.role, user.state, user.district)


def require(permission: str):
    def dependency(current: Principal = Depends(get_current_user)) -> Principal:
        if not current.can(permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Your role ({current.role_label}) cannot perform this action.")
        return current
    return dependency
