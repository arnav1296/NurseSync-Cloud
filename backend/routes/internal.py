"""Machine-to-machine routes, protected by a shared token (not a user login).

- POST /shift-change: called by the scheduled AWS Lambda at each shift change. Builds a
  shift report (every open shift, the patients still on each nurse and whether they've
  been handed off), stores it in S3 and emails reminders through SNS.
- POST /seed: one-off, loads the demo data into an empty database and creates the
  matching Cognito logins.
"""

import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from config import INTERNAL_API_TOKEN
from services import db
from services.identity import create_auth_user
from services.notify import notify, subscribe_staff
from services.storage import StorageUnavailable, put_json

router = APIRouter()

SEED_FILE = Path(__file__).resolve().parent.parent / "sql" / "seed.json"


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    if not INTERNAL_API_TOKEN or not hmac.compare_digest(x_internal_token, INTERNAL_API_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")


@router.post("/shift-change", dependencies=[Depends(require_internal_token)])
async def shift_change():
    now = datetime.now(timezone.utc)
    report = {"generated_at": now.isoformat(), "nurses": []}

    for shift in await db.list_open_shifts():
        patients = await db.list_patients_for_nurse(shift["nurse_id"])
        pending = await db.pending_handoff_patient_ids(shift["nurse_id"])
        waiting = [p for p in patients if p["id"] not in pending]
        report["nurses"].append(
            {
                "nurse": shift["full_name"],
                "shift_started_at": shift["started_at"],
                "patients": [
                    {
                        "full_name": p["full_name"],
                        "bed": p["bed"],
                        "handoff_sent": p["id"] in pending,
                    }
                    for p in patients
                ],
            }
        )
        if waiting:
            names = "\n".join(f"  - Bed {p['bed'] or '-'}: {p['full_name']}" for p in waiting)
            await notify(
                "NurseSync: shift change - handoffs due",
                f"Hi {shift['full_name']}, it's shift change. These patients have not been "
                f"handed off yet:\n{names}\n\nOpen NurseSync > Handoff to send them.",
                recipient=shift["email"],
            )

    key: Optional[str] = f"reports/shift-change-{now.strftime('%Y%m%d-%H%M')}.json"
    try:
        await put_json(key, report)
    except StorageUnavailable:
        key = None
    return {"open_shifts": len(report["nurses"]), "report_key": key}


class SeedRequest(BaseModel):
    password: str = Field(min_length=8, max_length=72)
    # optional: subscribe the staff emails to SNS (the demo emails are not real inboxes)
    subscribe_emails: bool = False


_COLUMNS = {
    "staff": ["id", "full_name", "email", "role", "ward", "active", "created_at"],
    "patients": ["id", "mrn", "full_name", "ward", "bed", "assigned_nurse_id",
                 "assigned_doctor_id", "status", "admitted_at", "discharged_at", "created_at"],
    "shifts": ["id", "nurse_id", "started_at", "ended_at", "status", "created_at"],
    "patient_notes": ["id", "patient_id", "author_id", "shift_id", "section", "body",
                      "source", "raw_transcript", "stt_confidence", "created_at"],
    "handoffs": ["id", "patient_id", "from_nurse_id", "to_nurse_id", "from_shift_id",
                 "details", "major_decisions", "status", "response_note", "sent_at",
                 "responded_at", "created_at"],
    "handoff_events": ["id", "handoff_id", "actor_id", "event", "note", "created_at"],
    "alerts": ["id", "patient_id", "raised_by", "doctor_id", "message", "status",
               "created_at", "acknowledged_at"],
}
_TIME_COLS = {"created_at", "admitted_at", "discharged_at", "started_at", "ended_at",
              "sent_at", "responded_at", "acknowledged_at"}
_UUID_COLS = {"id", "assigned_nurse_id", "assigned_doctor_id", "nurse_id", "patient_id",
              "author_id", "shift_id", "from_nurse_id", "to_nurse_id", "from_shift_id",
              "handoff_id", "actor_id", "raised_by", "doctor_id"}


def _convert(column: str, value):
    if value is None:
        return None
    if column in _TIME_COLS:
        return datetime.fromisoformat(value)
    if column in _UUID_COLS:
        return db._uuid(value)
    return value


@router.post("/seed", dependencies=[Depends(require_internal_token)])
async def seed(req: SeedRequest):
    """Load backend/sql/seed.json into an empty database and create Cognito logins."""
    pool = await db.pool()
    async with pool.acquire() as conn:
        if await conn.fetchval("select count(*) from staff"):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already seeded.")

    data = json.loads(SEED_FILE.read_text(encoding="utf8"))
    counts = {}
    async with pool.acquire() as conn:
        async with conn.transaction():
            for table, cols in _COLUMNS.items():
                rows = data.get(table, [])
                placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
                sql = f"insert into {table} ({', '.join(cols)}) values ({placeholders})"
                for row in rows:
                    await conn.execute(sql, *[_convert(c, row.get(c)) for c in cols])
                counts[table] = len(rows)

    # a Cognito login for every staff member, linked by `sub`
    logins = []
    for member in data.get("staff", []):
        sub = await create_auth_user(member["email"], req.password, member["role"])
        await db.link_staff_sub(member["id"], sub)
        if req.subscribe_emails:
            await subscribe_staff(member["email"])
        logins.append(member["email"])

    return {"inserted": counts, "logins": logins}
