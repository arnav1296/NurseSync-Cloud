"""Photos and documents on a patient, stored in Amazon S3.

Upload is two steps so file bytes never pass through the API: the client asks for a
presigned PUT URL, uploads straight to S3, then registers the object here. Only the
patient's nurse can attach; the nurse, a nurse receiving them in a handoff, and the
patient's doctor can view.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from services.access import ensure_assigned_patient, ensure_can_view_patient, ensure_doctor_patient
from services.auth import get_current_doctor, get_current_nurse
from services.db import insert_attachment, list_attachments
from services.storage import (
    ALLOWED_TYPES,
    StorageUnavailable,
    download_url,
    new_attachment_key,
    object_exists,
    upload_url,
)

router = APIRouter()


class UploadRequest(BaseModel):
    patient_id: str
    file_name: str = Field(min_length=1, max_length=200)
    content_type: str


class RegisterRequest(UploadRequest):
    s3_key: str = Field(min_length=1, max_length=400)


def _unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Attachments are unavailable right now.",
    )


def _with_urls(rows: list[dict]) -> list[dict]:
    return [{**row, "url": download_url(row["s3_key"])} for row in rows]


@router.post("/upload-url")
async def request_upload(req: UploadRequest, nurse: dict = Depends(get_current_nurse)):
    await ensure_assigned_patient(req.patient_id, nurse)
    if req.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Attach a photo (JPEG, PNG, WebP) or a PDF.",
        )
    key = new_attachment_key(req.patient_id, req.file_name)
    try:
        return {"upload_url": upload_url(key, req.content_type), "s3_key": key}
    except StorageUnavailable:
        raise _unavailable()


@router.post("")
async def register(req: RegisterRequest, nurse: dict = Depends(get_current_nurse)):
    await ensure_assigned_patient(req.patient_id, nurse)
    # the key must be one we issued for this patient, and the upload must have happened
    if not req.s3_key.startswith(f"attachments/{req.patient_id}/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown upload.")
    try:
        if not await object_exists(req.s3_key):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="The upload didn't finish."
            )
        row = await insert_attachment(
            req.patient_id, nurse["id"], req.s3_key, req.file_name, req.content_type
        )
        return {"attachment": _with_urls([row])[0]}
    except StorageUnavailable:
        raise _unavailable()


@router.get("/patient/{patient_id}")
async def for_patient(patient_id: str, nurse: dict = Depends(get_current_nurse)):
    await ensure_can_view_patient(patient_id, nurse)
    try:
        return {"attachments": _with_urls(await list_attachments(patient_id))}
    except StorageUnavailable:
        return {"attachments": []}


@router.get("/doctor/patient/{patient_id}")
async def for_doctor(patient_id: str, doctor: dict = Depends(get_current_doctor)):
    await ensure_doctor_patient(patient_id, doctor)
    try:
        return {"attachments": _with_urls(await list_attachments(patient_id))}
    except StorageUnavailable:
        return {"attachments": []}
