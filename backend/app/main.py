from __future__ import annotations
import logging, time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from . import llm, services
from .api import ROUTERS
from .config import get_settings
from .db import SessionLocal, init_db
from .risk import ENGINE_VERSION, ONTOLOGY_VERSION, TRANSPARENCY_NOTE

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("drishti")
settings = get_settings()
app = FastAPI(title="DRISHTI API", version=ENGINE_VERSION,
              description="MPLADS risk, evidence and verification intelligence.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    # Method, path, status and duration only. Never log credentials or payloads.
    logger.info("%s %s %s %.1fms", request.method, request.url.path, response.status_code,
                (time.perf_counter() - started) * 1000)
    return response


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    session = SessionLocal()
    try:
        services.sync_rules(session)
    finally:
        session.close()


@app.get("/api/health")
def health():
    return {"status": "ok", "environment": settings.environment,
            "engine_version": ENGINE_VERSION, "ontology_version": ONTOLOGY_VERSION,
            "llm": llm.model_metadata(), "transparency_note": TRANSPARENCY_NOTE}


for router in ROUTERS:
    app.include_router(router, prefix="/api")
