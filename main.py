from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
import os
import logging

from database import engine, Base
import models  # noqa: F401 — side-effect: registers all ORM models with Base

app = FastAPI(
    title="TutorU",
    description="AI-powered personalised learning platform",
)

# ---------------------------------------------------------------------------
# Rate limiter (SEC-3)
# ---------------------------------------------------------------------------
from routers.limiter import limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# Secret key
# ---------------------------------------------------------------------------
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    if os.environ.get('ENVIRONMENT') == 'production':
        raise ValueError("SECRET_KEY environment variable is not set in production!")
    import secrets
    secret_key = secrets.token_hex(32)

app.add_middleware(SessionMiddleware, secret_key=secret_key)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from routers import home, course, lesson, quiz, chat, api

app.include_router(home.router)
app.include_router(course.router)
app.include_router(lesson.router)
app.include_router(quiz.router)
app.include_router(chat.router)
app.include_router(api.router)

# ---------------------------------------------------------------------------
# Startup: schema creation + inline migrations + ChromaDB init
# ---------------------------------------------------------------------------

async def _apply_schema_migrations():
    """
    Apply any pending column additions that create_all() won't handle
    (SQLAlchemy's create_all does not ALTER existing tables).

    Each ALTER is wrapped in its own try/except so a single already-present
    column doesn't abort the rest. SQLite raises OperationalError
    ("duplicate column name") which we silently swallow.
    """
    new_columns = [
        # Phase 1 — added in the last session
        "ALTER TABLE lessons ADD COLUMN vector_indexed BOOLEAN DEFAULT 0 NOT NULL",
        # Phase 2 — pre-rendered markdown HTML
        "ALTER TABLE lessons ADD COLUMN content_html TEXT",
        # Phase 3 — background generation state
        "ALTER TABLE courses ADD COLUMN is_generating BOOLEAN DEFAULT 0 NOT NULL",
    ]
    async with engine.begin() as conn:
        for stmt in new_columns:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists — safe to ignore


@app.on_event("startup")
async def startup_event():
    # 1. Create all tables that don't yet exist (new installs)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Apply inline migrations for existing installs
    await _apply_schema_migrations()

    # 3. Lazy-initialise ChromaDB (heavy; runs in threadpool) (AI-9 / PERF-9)
    from fastapi.concurrency import run_in_threadpool
    from utils import init_vector_store
    await run_in_threadpool(init_vector_store)

    logging.info("TutorU startup complete.")


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------
from dependencies import render

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return render(request, "404.html", status_code=404)
    return render(request, "500.html", status_code=exc.status_code)

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logging.error("Unhandled exception", exc_info=True)
    return render(request, "500.html", status_code=500)
