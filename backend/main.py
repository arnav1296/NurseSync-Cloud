import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGIN_REGEX, ALLOWED_ORIGINS, DATABASE_URL
from routes import (
    admin,
    alerts,
    attachments,
    doctor,
    handoff,
    internal,
    notes,
    patients,
    shifts,
    staff,
)
from services import db

logging.basicConfig(level=logging.INFO)
SCHEMA = Path(__file__).resolve().parent / "sql" / "schema.sql"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # every statement is "if not exists", so applying it on each start is safe and
    # means a fresh RDS instance needs no separate migration step
    if DATABASE_URL:
        pool = await db.pool()
        async with pool.acquire() as conn:
            await conn.execute(SCHEMA.read_text(encoding="utf8"))
    yield
    await db.close_pool()


app = FastAPI(title="NurseSync API", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(staff.router, prefix="/api/staff", tags=["Staff"])
app.include_router(shifts.router, prefix="/api/shifts", tags=["Shifts"])
app.include_router(patients.router, prefix="/api/patients", tags=["Patients"])
app.include_router(notes.router, prefix="/api/notes", tags=["Notes"])
app.include_router(handoff.router, prefix="/api/handoff", tags=["Handoff"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(doctor.router, prefix="/api/doctor", tags=["Doctor"])
app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
app.include_router(attachments.router, prefix="/api/attachments", tags=["Attachments"])
app.include_router(internal.router, prefix="/api/internal", tags=["Internal"])


# /health for the load balancer; /api/health for checks through CloudFront
@app.get("/health")
@app.get("/api/health")
def health():
    return {"status": "NurseSync is live"}
