"""
app/main.py
────────────
FastAPI application entry point.

Startup sequence:
  1. Configure structured logging
  2. Create DB tables (if not exists) via SQLAlchemy
  3. Mount webhook + admin routers
  4. Expose health check endpoint

Run with:
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
import os
import sys
import asyncio

# Fix for psycopg async on Windows — must be set before any async code runs
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Force UTF-8 output on Windows (prevents emoji/unicode encoding errors)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

from contextlib import asynccontextmanager
from pathlib import Path
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routers import admin, webhook, web_api

# ── Logging setup ─────────────────────────────────────────────
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.log_level.upper(), logging.INFO)
    )
)
logger = structlog.get_logger(__name__)


# ── Lifecycle context ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all DB tables on startup and dispose engine on shutdown."""
    logger.info("Starting Spare Parts AI Assistant…")
    try:
        async with engine.begin() as conn:
            import app.models  # noqa: F401
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ready.")
    except Exception as exc:
        logger.warning(
            "Could not connect to database on startup: %s. "
            "Start PostgreSQL with: docker-compose up -d postgres",
            exc,
        )
    yield
    await engine.dispose()
    logger.info("Application shutdown complete.")


# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(
    title="Spare Parts AI Assistant",
    description=(
        "WhatsApp bot that diagnoses machine faults using AI, "
        "recommends spare parts, and sends YouTube repair tutorials."
    ),
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static Files ──────────────────────────────────────────────
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ── Routers ───────────────────────────────────────────────────
app.include_router(web_api.router)
app.include_router(webhook.router)
app.include_router(admin.router)


# ── Web UI Root & Monitoring ──────────────────────────────────
@app.api_route("/", methods=["GET", "HEAD"], tags=["ui"])
async def root():
    """Serves the interactive web UI dashboard."""
    index_file = Path(__file__).parent / "static" / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {
        "name": "Spare Parts AI Assistant",
        "status": "running",
        "docs": "/docs",
        "webhook": "/webhook",
        "admin": "/admin",
    }


@app.get("/health", tags=["monitoring"])
async def health_check():
    """Simple liveness probe — returns 200 if the app is running."""
    return JSONResponse({"status": "healthy", "version": "1.0.0"})


@app.get("/api/info", tags=["monitoring"])
async def api_info():
    """System information endpoint."""
    return {
        "name": "Spare Parts AI Assistant",
        "status": "running",
        "docs": "/docs",
        "webhook": "/webhook",
        "admin": "/admin",
    }
