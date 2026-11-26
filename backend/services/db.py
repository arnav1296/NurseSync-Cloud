"""Every query the API runs, against PostgreSQL on Amazon RDS.

One asyncpg connection pool per process. Functions return plain dicts shaped exactly
as the routes and the client expect: ids and timestamps as strings, and related rows
nested (``author``, ``patient``, ``from_nurse``...) as small objects built with
``json_build_object``. The database is in a private subnet and only the API can
reach it, so access control lives in services/auth.py and services/access.py.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Optional

import asyncpg

from config import DATABASE_URL

_pool: Optional[asyncpg.Pool] = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # json_build_object(...) comes back as json; decode it into dicts
    for name in ("json", "jsonb"):
        await conn.set_type_codec(name, encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set.")
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=1, max_size=10, init=_init_connection
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _value(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _row(record: Optional[asyncpg.Record]) -> Optional[dict]:
    return None if record is None else {k: _value(v) for k, v in record.items()}


def _rows(records: list) -> list[dict]:
    return [_row(r) for r in records]


def _uuid(value: Any) -> Optional[uuid.UUID]:
    """Ids arrive as strings from URLs; a malformed one simply matches nothing."""
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _fetch(sql: str, *args) -> list[dict]:
    async with (await pool()).acquire() as conn:
        return _rows(await conn.fetch(sql, *args))


async def _fetchrow(sql: str, *args) -> Optional[dict]:
    async with (await pool()).acquire() as conn:
        return _row(await conn.fetchrow(sql, *args))


async def _fetchval(sql: str, *args) -> Any:
    async with (await pool()).acquire() as conn:
        return await conn.fetchval(sql, *args)


async def _execute(sql: str, *args) -> None:
    async with (await pool()).acquire() as conn:
        await conn.execute(sql, *args)


# nested objects, reused across queries
_STAFF_REF = "json_build_object('id', {a}.id, 'full_name', {a}.full_name)"
_PATIENT_REF = (
    "json_build_object('id', {a}.id, 'full_name', {a}.full_name, 'mrn', {a}.mrn, "
    "'ward', {a}.ward, 'bed', {a}.bed)"
)


def _staff_ref(alias: str) -> str:
    return f"case when {alias}.id is null then null else {_STAFF_REF.format(a=alias)} end"


# --------------------------------------------------------------------------
# staff
# --------------------------------------------------------------------------

_STAFF_FIELDS = "id, full_name, email, role, ward, active, created_at"


async def get_staff(staff_id: str) -> Optional[dict]:
    sid = _uuid(staff_id)
    if sid is None:
        return None
    return await _fetchrow(f"select {_STAFF_FIELDS} from staff where id = $1", sid)


async def get_staff_by_sub(sub: str) -> Optional[dict]:
    """The staff row linked to a Cognito user."""
    return await _fetchrow(f"select {_STAFF_FIELDS} from staff where auth_sub = $1", sub)


async def list_nurses(exclude_id: Optional[str] = None) -> list[dict]:
    return await _fetch(
        "select id, full_name, email, ward from staff "
        "where role = 'nurse' and active and ($1::uuid is null or id <> $1) "
        "order by full_name",
        _uuid(exclude_id),
    )


# --------------------------------------------------------------------------
# shifts
# --------------------------------------------------------------------------

async def get_active_shift(nurse_id: str) -> Optional[dict]:
    return await _fetchrow(
        "select * from shifts where nurse_id = $1 and status = 'active' limit 1",
        _uuid(nurse_id),
    )


async def create_shift(nurse_id: str) -> dict:
    return await _fetchrow(
        "insert into shifts (nurse_id, status) values ($1, 'active') returning *",
        _uuid(nurse_id),
    )


async def close_shift(shift_id: str) -> dict:
    row = await _fetchrow(
        "update shifts set status = 'closed', ended_at = now() where id = $1 returning *",
        _uuid(shift_id),
    )
    return row or {}


async def nurses_on_shift() -> set[str]:
    rows = await _fetch("select nurse_id from shifts where status = 'active'")
    return {r["nurse_id"] for r in rows}


async def list_open_shifts() -> list[dict]:
    """Every open shift with its nurse, for the shift-change job."""
    return await _fetch(
        "select s.id, s.nurse_id, s.started_at, n.full_name, n.email "
        "from shifts s join staff n on n.id = s.nurse_id "
        "where s.status = 'active' order by n.full_name"
    )


# --------------------------------------------------------------------------
# patients
# --------------------------------------------------------------------------

_PATIENT_FIELDS = (
    "p.id, p.mrn, p.full_name, p.ward, p.bed, p.status, p.admitted_at, p.discharged_at, "
    "p.assigned_nurse_id, p.assigned_doctor_id"
)


async def list_patients_for_nurse(nurse_id: str) -> list[dict]:
    return await _fetch(
        f"select {_PATIENT_FIELDS} from patients p "
        "where p.assigned_nurse_id = $1 and p.status = 'admitted' order by p.bed",
        _uuid(nurse_id),
    )


async def list_patients_for_doctor(doctor_id: str) -> list[dict]:
    return await _fetch(
        f"select {_PATIENT_FIELDS}, {_staff_ref('n')} as nurse "
        "from patients p left join staff n on n.id = p.assigned_nurse_id "
        "where p.assigned_doctor_id = $1 and p.status = 'admitted' order by p.bed",
        _uuid(doctor_id),
    )


async def get_patient(patient_id: str) -> Optional[dict]:
    pid = _uuid(patient_id)
    if pid is None:
        return None
    return await _fetchrow(f"select {_PATIENT_FIELDS} from patients p where p.id = $1", pid)


async def reassign_patient(patient_id: str, nurse_id: str) -> None:
    await _execute(
        "update patients set assigned_nurse_id = $2 where id = $1",
        _uuid(patient_id),
        _uuid(nurse_id),
    )


async def has_pending_handoff_to(patient_id: str, nurse_id: str) -> bool:
    return bool(
        await _fetchval(
            "select exists(select 1 from handoffs where patient_id = $1 "
            "and to_nurse_id = $2 and status = 'pending')",
            _uuid(patient_id),
            _uuid(nurse_id),
        )
    )


# --------------------------------------------------------------------------
# patient notes
# --------------------------------------------------------------------------

async def insert_note(
    patient_id: str,
    author_id: str,
    shift_id: Optional[str],
    section: str,
    body: str,
    source: str = "typed",
    raw_transcript: Optional[str] = None,
    stt_confidence: Optional[float] = None,
) -> dict:
    return await _fetchrow(
        "insert into patient_notes "
        "(patient_id, author_id, shift_id, section, body, source, raw_transcript, stt_confidence) "
        "values ($1, $2, $3, $4, $5, $6, $7, $8) returning *",
        _uuid(patient_id),
        _uuid(author_id),
        _uuid(shift_id),
        section,
        body,
        source,
        raw_transcript,
        stt_confidence,
    )


async def list_notes(patient_id: str, section: Optional[str] = None) -> list[dict]:
    return await _fetch(
        f"select n.*, {_staff_ref('a')} as author "
        "from patient_notes n left join staff a on a.id = n.author_id "
        "where n.patient_id = $1 and ($2::text is null or n.section = $2) "
        "order by n.created_at desc",
        _uuid(patient_id),
        section,
    )


async def list_notes_for_handoff(patient_id: str, shift_id: str) -> list[dict]:
    """Notes the outgoing nurse accumulated this shift — the raw material the
    handoff draft is composed from."""
    return await _fetch(
        "select section, body, created_at from patient_notes "
        "where patient_id = $1 and shift_id = $2 order by created_at",
        _uuid(patient_id),
        _uuid(shift_id),
    )


async def count_notes_by_patient(patient_ids: list[str]) -> dict[str, dict]:
    """Note count + latest activity per patient, for the My Patients list."""
    ids = [i for i in (_uuid(p) for p in patient_ids) if i is not None]
    if not ids:
        return {}
    rows = await _fetch(
        "select patient_id, count(*) as note_count, max(created_at) as last_note_at "
        "from patient_notes where patient_id = any($1::uuid[]) group by patient_id",
        ids,
    )
    return {
        r["patient_id"]: {"note_count": r["note_count"], "last_note_at": r["last_note_at"]}
        for r in rows
    }


# --------------------------------------------------------------------------
# alerts
# --------------------------------------------------------------------------

_ALERT_SELECT = (
    "select al.*, "
    f"{_PATIENT_REF.format(a='p')} as patient, "
    f"{_staff_ref('rb')} as raised_by_staff, "
    f"{_staff_ref('d')} as doctor "
    "from alerts al "
    "join patients p on p.id = al.patient_id "
    "left join staff rb on rb.id = al.raised_by "
    "left join staff d on d.id = al.doctor_id "
)


async def insert_alert(
    patient_id: str, raised_by: str, doctor_id: str, message: Optional[str]
) -> dict:
    return await _fetchrow(
        "insert into alerts (patient_id, raised_by, doctor_id, message) "
        "values ($1, $2, $3, $4) returning *",
        _uuid(patient_id),
        _uuid(raised_by),
        _uuid(doctor_id),
        message,
    )


async def get_alert(alert_id: str) -> Optional[dict]:
    aid = _uuid(alert_id)
    if aid is None:
        return None
    return await _fetchrow(_ALERT_SELECT + "where al.id = $1", aid)


async def list_alerts_for_patient(patient_id: str) -> list[dict]:
    return await _fetch(
        _ALERT_SELECT + "where al.patient_id = $1 order by al.created_at desc",
        _uuid(patient_id),
    )


async def list_open_alerts(doctor_id: str) -> list[dict]:
    return await _fetch(
        _ALERT_SELECT + "where al.doctor_id = $1 and al.status = 'open' "
        "order by al.created_at desc",
        _uuid(doctor_id),
    )


async def list_acknowledged_alerts(doctor_id: str, limit: int = 30) -> list[dict]:
    return await _fetch(
        _ALERT_SELECT + "where al.doctor_id = $1 and al.status = 'acknowledged' "
        "order by al.acknowledged_at desc limit $2",
        _uuid(doctor_id),
        limit,
    )


async def acknowledge_alert(alert_id: str) -> dict:
    # the first acknowledgement's time is the one that counts
    row = await _fetchrow(
        "update alerts set status = 'acknowledged', acknowledged_at = now() "
        "where id = $1 and status = 'open' returning *",
        _uuid(alert_id),
    )
    return row or {}


async def count_open_alerts() -> int:
    return await _fetchval("select count(*) from alerts where status = 'open'")


# --------------------------------------------------------------------------
# handoffs
# --------------------------------------------------------------------------

_HANDOFF_SELECT = (
    "select h.*, "
    f"{_PATIENT_REF.format(a='p')} as patient, "
    f"{_staff_ref('f')} as from_nurse, "
    f"{_staff_ref('t')} as to_nurse "
    "from handoffs h "
    "join patients p on p.id = h.patient_id "
    "left join staff f on f.id = h.from_nurse_id "
    "left join staff t on t.id = h.to_nurse_id "
)


async def insert_handoffs(rows: list[dict]) -> list[dict]:
    """All or nothing: one patient refused (e.g. already pending) sends none."""
    created = []
    async with (await pool()).acquire() as conn:
        async with conn.transaction():
            for row in rows:
                record = await conn.fetchrow(
                    "insert into handoffs (patient_id, from_nurse_id, to_nurse_id, "
                    "from_shift_id, details, major_decisions, status) "
                    "values ($1, $2, $3, $4, $5, $6, $7) returning *",
                    _uuid(row["patient_id"]),
                    _uuid(row["from_nurse_id"]),
                    _uuid(row["to_nurse_id"]),
                    _uuid(row.get("from_shift_id")),
                    row.get("details"),
                    row.get("major_decisions"),
                    row.get("status", "pending"),
                )
                created.append(_row(record))
    return created


async def get_handoff(handoff_id: str) -> Optional[dict]:
    hid = _uuid(handoff_id)
    if hid is None:
        return None
    return await _fetchrow(_HANDOFF_SELECT + "where h.id = $1", hid)


async def list_inbox(nurse_id: str) -> list[dict]:
    return await _fetch(
        _HANDOFF_SELECT + "where h.to_nurse_id = $1 and h.status = 'pending' "
        "order by h.sent_at desc",
        _uuid(nurse_id),
    )


async def list_sent(nurse_id: str, limit: int = 50) -> list[dict]:
    return await _fetch(
        _HANDOFF_SELECT + "where h.from_nurse_id = $1 order by h.sent_at desc limit $2",
        _uuid(nurse_id),
        limit,
    )


async def respond_to_handoff(
    handoff_id: str, status: str, response_note: Optional[str]
) -> dict:
    row = await _fetchrow(
        "update handoffs set status = $2, response_note = $3, responded_at = now() "
        "where id = $1 and status = 'pending' returning *",  # a handoff is answered once
        _uuid(handoff_id),
        status,
        response_note,
    )
    return row or {}


async def pending_handoff_patient_ids(nurse_id: str) -> set[str]:
    rows = await _fetch(
        "select patient_id from handoffs where from_nurse_id = $1 and status = 'pending'",
        _uuid(nurse_id),
    )
    return {r["patient_id"] for r in rows}


async def has_pending_handoff(patient_id: str) -> bool:
    return bool(
        await _fetchval(
            "select exists(select 1 from handoffs where patient_id = $1 and status = 'pending')",
            _uuid(patient_id),
        )
    )


async def has_pending_handoffs_involving(nurse_id: str) -> bool:
    return bool(
        await _fetchval(
            "select exists(select 1 from handoffs where status = 'pending' "
            "and (from_nurse_id = $1 or to_nurse_id = $1))",
            _uuid(nurse_id),
        )
    )


async def insert_handoff_event(
    handoff_id: str, actor_id: str, event: str, note: Optional[str] = None
) -> None:
    await _execute(
        "insert into handoff_events (handoff_id, actor_id, event, note) values ($1, $2, $3, $4)",
        _uuid(handoff_id),
        _uuid(actor_id),
        event,
        note,
    )


async def list_handoff_events(handoff_id: str) -> list[dict]:
    return await _fetch(
        f"select e.*, {_staff_ref('s')} as actor "
        "from handoff_events e left join staff s on s.id = e.actor_id "
        "where e.handoff_id = $1 order by e.created_at",
        _uuid(handoff_id),
    )


async def list_handoff_timings() -> list[dict]:
    return await _fetch("select status, sent_at, responded_at from handoffs")


# --------------------------------------------------------------------------
# admin
# --------------------------------------------------------------------------

async def list_all_staff() -> list[dict]:
    """Every account, inactive ones included, so they can be reactivated."""
    return await _fetch(
        "select id, full_name, email, role, ward, active from staff order by role, full_name"
    )


async def get_staff_by_email(email: str) -> Optional[dict]:
    return await _fetchrow("select id from staff where email = $1", email)


async def insert_staff(row: dict) -> dict:
    return await _fetchrow(
        "insert into staff (auth_sub, full_name, email, role, ward, active) "
        "values ($1, $2, $3, $4, $5, $6) returning " + _STAFF_FIELDS,
        row.get("auth_sub"),
        row["full_name"],
        row["email"],
        row["role"],
        row.get("ward"),
        row.get("active", True),
    )


async def set_staff_active(staff_id: str, active: bool) -> dict:
    row = await _fetchrow(
        f"update staff set active = $2 where id = $1 returning {_STAFF_FIELDS}",
        _uuid(staff_id),
        active,
    )
    return row or {}


async def link_staff_sub(staff_id: str, sub: str) -> None:
    await _execute("update staff set auth_sub = $2 where id = $1", _uuid(staff_id), sub)


async def list_patients_by_status(status: str = "admitted") -> list[dict]:
    # the ward roster reads by bed; history reads newest discharge first
    order = "p.discharged_at desc" if status == "discharged" else "p.bed"
    return await _fetch(
        f"select {_PATIENT_FIELDS}, {_staff_ref('n')} as nurse, {_staff_ref('d')} as doctor "
        "from patients p "
        "left join staff n on n.id = p.assigned_nurse_id "
        "left join staff d on d.id = p.assigned_doctor_id "
        f"where p.status = $1 order by {order}",
        status,
    )


async def list_admitted_patients() -> list[dict]:
    return await list_patients_by_status("admitted")


async def get_patient_by_mrn(mrn: str) -> Optional[dict]:
    return await _fetchrow("select id from patients where mrn = $1", mrn)


async def insert_patient(row: dict) -> dict:
    return await _fetchrow(
        "insert into patients (mrn, full_name, ward, bed, assigned_nurse_id, "
        "assigned_doctor_id, status) values ($1, $2, $3, $4, $5, $6, $7) "
        "returning id, mrn, full_name, ward, bed, status, admitted_at, discharged_at, "
        "assigned_nurse_id, assigned_doctor_id",
        row["mrn"],
        row["full_name"],
        row.get("ward"),
        row.get("bed"),
        _uuid(row.get("assigned_nurse_id")),
        _uuid(row.get("assigned_doctor_id")),
        row.get("status", "admitted"),
    )


async def discharge_patient(patient_id: str) -> dict:
    row = await _fetchrow(
        "update patients set status = 'discharged', discharged_at = now() "
        "where id = $1 and status = 'admitted' "  # discharged once
        "returning id, mrn, full_name, ward, bed, status, admitted_at, discharged_at, "
        "assigned_nurse_id, assigned_doctor_id",
        _uuid(patient_id),
    )
    return row or {}


_ASSIGNABLE = {"assigned_nurse_id", "assigned_doctor_id"}


async def update_patient_assignment(patient_id: str, fields: dict) -> dict:
    columns = [c for c in fields if c in _ASSIGNABLE]
    if not columns:
        return await get_patient(patient_id) or {}
    sets = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(columns))
    row = await _fetchrow(
        f"update patients set {sets} where id = $1 "
        "returning id, mrn, full_name, ward, bed, status, admitted_at, discharged_at, "
        "assigned_nurse_id, assigned_doctor_id",
        _uuid(patient_id),
        *[_uuid(fields[c]) for c in columns],
    )
    return row or {}


# --------------------------------------------------------------------------
# attachments (S3 objects on a patient)
# --------------------------------------------------------------------------

async def insert_attachment(
    patient_id: str, uploaded_by: str, s3_key: str, file_name: str, content_type: str
) -> dict:
    return await _fetchrow(
        "insert into attachments (patient_id, uploaded_by, s3_key, file_name, content_type) "
        "values ($1, $2, $3, $4, $5) returning *",
        _uuid(patient_id),
        _uuid(uploaded_by),
        s3_key,
        file_name,
        content_type,
    )


async def list_attachments(patient_id: str) -> list[dict]:
    return await _fetch(
        f"select at.*, {_staff_ref('s')} as uploader "
        "from attachments at left join staff s on s.id = at.uploaded_by "
        "where at.patient_id = $1 order by at.created_at desc",
        _uuid(patient_id),
    )
