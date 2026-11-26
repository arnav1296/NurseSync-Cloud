"""The administrator's screen: staff accounts, patient assignments, and the
handoff metrics the project is measured by. Admins never touch the clinical
record itself — no notes, no handoffs, no alerts."""

import asyncio
from datetime import datetime
from statistics import median
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from services.auth import get_current_admin
from services.db import (
    count_open_alerts,
    discharge_patient,
    get_patient,
    get_patient_by_mrn,
    get_staff,
    get_staff_by_email,
    has_pending_handoff,
    has_pending_handoffs_involving,
    insert_patient,
    insert_staff,
    list_admitted_patients,
    list_all_staff,
    list_handoff_timings,
    list_patients_by_status,
    list_patients_for_doctor,
    list_patients_for_nurse,
    nurses_on_shift,
    set_staff_active,
    update_patient_assignment,
)
from services.identity import create_auth_user, delete_auth_user
from services.notify import subscribe_staff

router = APIRouter()


class CreateStaffRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    role: Literal["nurse", "doctor"]
    ward: Optional[str] = Field(default=None, max_length=60)
    password: str = Field(min_length=8, max_length=72)


class AssignmentRequest(BaseModel):
    nurse_id: Optional[str] = None
    doctor_id: Optional[str] = None


class AdmitPatientRequest(BaseModel):
    mrn: str = Field(min_length=1, max_length=40)
    full_name: str = Field(min_length=1, max_length=120)
    ward: Optional[str] = Field(default=None, max_length=60)
    bed: Optional[str] = Field(default=None, max_length=20)
    nurse_id: str
    doctor_id: Optional[str] = None


# --------------------------------------------------------------------------
# staff
# --------------------------------------------------------------------------

@router.get("/staff")
async def staff_list(admin: dict = Depends(get_current_admin)):
    staff, patients, on_shift = await asyncio.gather(
        list_all_staff(), list_admitted_patients(), nurses_on_shift()
    )

    counts: dict[str, int] = {}
    for patient in patients:
        for key in ("assigned_nurse_id", "assigned_doctor_id"):
            if patient.get(key):
                counts[patient[key]] = counts.get(patient[key], 0) + 1

    for member in staff:
        member["patient_count"] = counts.get(member["id"], 0)
        # a shift opens when a nurse signs in and closes when she ends it
        member["on_shift"] = member["id"] in on_shift
    return {"staff": staff, "count": len(staff)}


@router.post("/staff")
async def create_staff(req: CreateStaffRequest, admin: dict = Depends(get_current_admin)):
    email = req.email.strip().lower()
    full_name = req.full_name.strip()
    if "@" not in email or not full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter a full name and a valid email address.",
        )
    if await get_staff_by_email(email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Someone on the roster already uses that email.",
        )

    try:
        sub = await create_auth_user(email, req.password, req.role)
    except Exception as exc:
        # Cognito refuses an email it already knows, even without a staff row
        detail = str(exc)
        if "UsernameExists" in detail or "already" in detail.lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A login with that email already exists.",
            )
        if "InvalidPassword" in detail:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The password needs at least 8 characters with a number and a letter.",
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Couldn't create the login: {detail}",
        )

    try:
        member = await insert_staff(
            {
                "auth_sub": sub,
                "full_name": full_name,
                "email": email,
                "role": req.role,
                "ward": (req.ward or "").strip() or None,
                "active": True,
            }
        )
    except Exception:
        # a login with no staff row can sign in but do nothing; don't leave one behind
        await delete_auth_user(email)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Couldn't add this person to the roster. Nothing was saved.",
        )

    # their alerts and handoffs reach them by email once they confirm the subscription
    await subscribe_staff(email)
    return {"staff": {**member, "patient_count": 0, "on_shift": False}}


async def _load_staff(staff_id: str) -> dict:
    member = await get_staff(staff_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Staff member not found."
        )
    return member


@router.post("/staff/{staff_id}/deactivate")
async def deactivate(staff_id: str, admin: dict = Depends(get_current_admin)):
    if staff_id == admin["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't deactivate your own account.",
        )
    member = await _load_staff(staff_id)
    if not member["active"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This account is already inactive."
        )

    # same rule as ending a shift: nobody leaves with patients still on their name
    if member["role"] == "nurse":
        patients = await list_patients_for_nurse(staff_id)
    elif member["role"] == "doctor":
        patients = await list_patients_for_doctor(staff_id)
    else:
        patients = []

    if patients:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Reassign these patients before deactivating this account.",
                "patients": [
                    {"id": p["id"], "full_name": p["full_name"], "bed": p["bed"]}
                    for p in patients
                ],
            },
        )
    if member["role"] == "nurse" and await has_pending_handoffs_involving(staff_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This nurse has a handoff awaiting a response. Let it be answered first.",
        )

    # takes effect on their next request: get_current_staff rejects inactive accounts
    updated = await set_staff_active(staff_id, False)
    return {"staff": updated}


@router.post("/staff/{staff_id}/reactivate")
async def reactivate(staff_id: str, admin: dict = Depends(get_current_admin)):
    member = await _load_staff(staff_id)
    if member["active"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This account is already active."
        )
    updated = await set_staff_active(staff_id, True)
    return {"staff": updated}


# --------------------------------------------------------------------------
# patient assignment
# --------------------------------------------------------------------------

@router.get("/patients")
async def patients_list(
    status_filter: Literal["admitted", "discharged"] = Query(default="admitted", alias="status"),
    admin: dict = Depends(get_current_admin),
):
    """Admitted patients by bed, or the discharged history newest first. Nurses
    and doctors only ever see admitted patients."""
    patients = await list_patients_by_status(status_filter)
    return {"patients": patients, "count": len(patients)}


async def _ensure_active(staff_id: str, role: str) -> None:
    member = await get_staff(staff_id)
    if not member or member["role"] != role or not member["active"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The selected {role} is not an active {role}.",
        )


async def _load_admitted(patient_id: str) -> dict:
    patient = await get_patient(patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found."
        )
    if patient["status"] != "admitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This patient has been discharged.",
        )
    return patient


@router.post("/patients")
async def admit(req: AdmitPatientRequest, admin: dict = Depends(get_current_admin)):
    mrn = req.mrn.strip().upper()
    full_name = req.full_name.strip()
    if not mrn or not full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enter the patient's MRN and full name.",
        )
    if await get_patient_by_mrn(mrn):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with that MRN already exists.",
        )

    # every admitted patient has a nurse from the first minute
    await _ensure_active(req.nurse_id, "nurse")
    if req.doctor_id:
        await _ensure_active(req.doctor_id, "doctor")

    patient = await insert_patient(
        {
            "mrn": mrn,
            "full_name": full_name,
            "ward": (req.ward or "").strip() or None,
            "bed": (req.bed or "").strip() or None,
            "assigned_nurse_id": req.nurse_id,
            "assigned_doctor_id": req.doctor_id or None,
            "status": "admitted",
        }
    )
    return {"patient": patient}


@router.post("/patients/{patient_id}/discharge")
async def discharge(patient_id: str, admin: dict = Depends(get_current_admin)):
    await _load_admitted(patient_id)
    # the incoming nurse could still accept it and take on a patient who has left
    if await has_pending_handoff(patient_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This patient has a handoff awaiting a response. Let it be answered first.",
        )

    updated = await discharge_patient(patient_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This patient has already been discharged.",
        )
    # notes, handoffs and alerts stay on the record; the patient just leaves
    # every nurse and doctor list, which only show admitted patients
    return {"patient": updated}


@router.patch("/patients/{patient_id}")
async def assign(
    patient_id: str, req: AssignmentRequest, admin: dict = Depends(get_current_admin)
):
    patient = await _load_admitted(patient_id)

    fields: dict[str, str] = {}
    if req.nurse_id and req.nurse_id != patient["assigned_nurse_id"]:
        await _ensure_active(req.nurse_id, "nurse")
        # the pending handoff would still name the old nurse as sender, and
        # accepting it would quietly undo this reassignment
        if await has_pending_handoff(patient_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This patient has a handoff awaiting a response. Let it be answered first.",
            )
        fields["assigned_nurse_id"] = req.nurse_id
    if req.doctor_id and req.doctor_id != patient["assigned_doctor_id"]:
        await _ensure_active(req.doctor_id, "doctor")
        fields["assigned_doctor_id"] = req.doctor_id

    if not fields:
        return {"patient": patient, "changed": False}

    updated = await update_patient_assignment(patient_id, fields)
    return {"patient": updated, "changed": True}


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def _minutes_between(start: str, end: str) -> float:
    return (
        datetime.fromisoformat(end) - datetime.fromisoformat(start)
    ).total_seconds() / 60


@router.get("/metrics")
async def metrics(admin: dict = Depends(get_current_admin)):
    """Time-to-acknowledgement and the clean-accept rate, straight from the
    stored timestamps — the numbers the proposal said the project would be judged by."""
    handoffs, open_alerts, on_shift, staff = await asyncio.gather(
        list_handoff_timings(), count_open_alerts(), nurses_on_shift(), list_all_staff()
    )
    active_nurses = [s for s in staff if s["role"] == "nurse" and s["active"]]

    by_status: dict[str, int] = {
        "pending": 0,
        "accepted": 0,
        "declined": 0,
        "issue_reported": 0,
    }
    tta: list[float] = []
    for row in handoffs:
        by_status[row["status"]] = by_status.get(row["status"], 0) + 1
        if row.get("responded_at"):
            tta.append(_minutes_between(row["sent_at"], row["responded_at"]))

    responded = len(tta)
    return {
        "handoffs_total": len(handoffs),
        "by_status": by_status,
        "responded": responded,
        "avg_tta_minutes": round(sum(tta) / responded, 1) if responded else None,
        "median_tta_minutes": round(median(tta), 1) if responded else None,
        "clean_accept_rate": (
            round(by_status["accepted"] / responded, 3) if responded else None
        ),
        "open_alerts": open_alerts,
        "nurses_on_shift": sum(1 for n in active_nurses if n["id"] in on_shift),
        "nurses_active": len(active_nurses),
    }
