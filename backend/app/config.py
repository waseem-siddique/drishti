"""Central configuration. Model ids and secrets live in the environment only."""
from __future__ import annotations
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]


def _load_env_file() -> None:
    for candidate in (ROOT / ".env", ROOT / "backend" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    jwt_secret: str
    session_minutes: int
    upload_dir: str
    evidence_dir: str
    max_upload_mb: int
    similarity_backend: str
    llm_provider: str
    llm_model: str
    llm_api_key: str
    cors_origins: List[str]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file()
    origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return Settings(
        environment=os.getenv("ENVIRONMENT", "local"),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./drishti.db"),
        jwt_secret=os.getenv("JWT_SECRET", "dev-only-secret-change-me"),
        session_minutes=int(os.getenv("SESSION_MINUTES", "480")),
        upload_dir=os.getenv("UPLOAD_DIR", "./var/uploads"),
        evidence_dir=os.getenv("EVIDENCE_DIR", "./var/evidence"),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "64")),
        similarity_backend=os.getenv("SIMILARITY_BACKEND", "lexical"),
        llm_provider=os.getenv("LLM_PROVIDER", "anthropic"),
        llm_model=os.getenv("LLM_MODEL", "claude-opus-5"),
        llm_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        cors_origins=[item.strip() for item in origins.split(",") if item.strip()],
    )
