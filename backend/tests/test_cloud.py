"""The AWS-facing pieces: Cognito token identity, internal routes, S3 attachments."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import main
from routes import attachments as attachments_routes
from routes import internal as internal_routes
from services import access as access_module
from services import auth as auth_module
from tests.conftest import PATIENT_ID, PRIYA, patient

TOKEN = "internal-secret"


# ---------------------------------------------------------------- Cognito identity

@pytest.fixture
def cognito(monkeypatch):
    state = {"claims": {"sub": "sub-priya"}, "staff": {**PRIYA}, "verify_error": False}

    def fake_verify(token):
        if state["verify_error"]:
            raise ValueError("bad signature")
        return state["claims"]

    async def get_staff_by_sub(sub):
        return state["staff"] if sub == "sub-priya" else None

    monkeypatch.setattr(auth_module, "_verify", fake_verify)
    monkeypatch.setattr(auth_module, "get_staff_by_sub", get_staff_by_sub)
    return state


async def _staff(header):
    return await auth_module.get_current_staff(authorization=header)


@pytest.mark.anyio
async def test_valid_token_resolves_the_linked_staff_member(cognito):
    staff = await _staff("Bearer abc")
    assert staff["id"] == PRIYA["id"]


@pytest.mark.anyio
async def test_missing_bearer_is_401(cognito):
    with pytest.raises(HTTPException) as err:
        await _staff("")
    assert err.value.status_code == 401


@pytest.mark.anyio
async def test_bad_token_is_401(cognito):
    cognito["verify_error"] = True
    with pytest.raises(HTTPException) as err:
        await _staff("Bearer forged")
    assert err.value.status_code == 401


@pytest.mark.anyio
async def test_login_with_no_staff_row_is_403(cognito):
    cognito["claims"] = {"sub": "someone-else"}
    with pytest.raises(HTTPException) as err:
        await _staff("Bearer abc")
    assert err.value.status_code == 403


@pytest.mark.anyio
async def test_deactivated_account_is_403(cognito):
    cognito["staff"]["active"] = False
    with pytest.raises(HTTPException) as err:
        await _staff("Bearer abc")
    assert err.value.status_code == 403


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---------------------------------------------------------------- internal routes

@pytest.fixture
def shift_change(monkeypatch):
    state = {"notified": [], "reports": []}

    async def list_open_shifts():
        return [{"id": "s1", "nurse_id": PRIYA["id"], "started_at": "2026-11-27T07:00:00+00:00",
                 "full_name": PRIYA["full_name"], "email": PRIYA["email"]}]

    async def list_patients_for_nurse(nurse_id):
        return [patient(), {**patient(), "id": "p2", "full_name": "Second Patient", "bed": "7"}]

    async def pending_handoff_patient_ids(nurse_id):
        return {PATIENT_ID}

    async def notify(subject, message, recipient=None):
        state["notified"].append((recipient, message))

    async def put_json(key, payload):
        state["reports"].append((key, payload))

    monkeypatch.setattr(internal_routes.db, "list_open_shifts", list_open_shifts)
    monkeypatch.setattr(internal_routes.db, "list_patients_for_nurse", list_patients_for_nurse)
    monkeypatch.setattr(internal_routes.db, "pending_handoff_patient_ids", pending_handoff_patient_ids)
    monkeypatch.setattr(internal_routes, "notify", notify)
    monkeypatch.setattr(internal_routes, "put_json", put_json)
    monkeypatch.setattr(internal_routes, "INTERNAL_API_TOKEN", TOKEN)
    return state


def test_internal_routes_refuse_without_the_token(shift_change):
    with TestClient(main.app) as client:
        assert client.post("/api/internal/shift-change").status_code == 403
        assert client.post(
            "/api/internal/shift-change", headers={"X-Internal-Token": "wrong"}
        ).status_code == 403


def test_shift_change_reports_and_reminds_only_about_unhanded_patients(shift_change):
    with TestClient(main.app) as client:
        response = client.post("/api/internal/shift-change", headers={"X-Internal-Token": TOKEN})
    assert response.status_code == 200
    assert response.json()["open_shifts"] == 1
    # one reminder, naming only the patient without a pending handoff
    (recipient, message), = shift_change["notified"]
    assert recipient == PRIYA["email"]
    assert "Second Patient" in message and "Ishan Verma" not in message
    key, report = shift_change["reports"][0]
    assert key.startswith("reports/shift-change-")
    assert [p["handoff_sent"] for p in report["nurses"][0]["patients"]] == [True, False]


# ---------------------------------------------------------------- attachments

@pytest.fixture
def storage(monkeypatch):
    state = {"exists": True, "inserted": []}

    async def get_patient(patient_id):
        return patient()

    async def object_exists(key):
        return state["exists"]

    async def insert_attachment(patient_id, uploaded_by, s3_key, file_name, content_type):
        row = {"id": "a1", "patient_id": patient_id, "uploaded_by": uploaded_by,
               "s3_key": s3_key, "file_name": file_name, "content_type": content_type}
        state["inserted"].append(row)
        return row

    monkeypatch.setattr(access_module, "get_patient", get_patient)
    monkeypatch.setattr(attachments_routes, "object_exists", object_exists)
    monkeypatch.setattr(attachments_routes, "insert_attachment", insert_attachment)
    monkeypatch.setattr(attachments_routes, "upload_url", lambda key, ct: f"https://s3/put/{key}")
    monkeypatch.setattr(attachments_routes, "download_url", lambda key: f"https://s3/get/{key}")
    return state


def test_upload_url_is_scoped_to_the_patient(as_priya, storage):
    response = as_priya.post(
        "/api/attachments/upload-url",
        json={"patient_id": PATIENT_ID, "file_name": "wound photo.jpg", "content_type": "image/jpeg"},
    )
    assert response.status_code == 200
    assert response.json()["s3_key"].startswith(f"attachments/{PATIENT_ID}/")


def test_only_images_and_pdfs_can_be_attached(as_priya, storage):
    response = as_priya.post(
        "/api/attachments/upload-url",
        json={"patient_id": PATIENT_ID, "file_name": "x.exe", "content_type": "application/x-msdownload"},
    )
    assert response.status_code == 400


def test_register_refuses_a_key_for_another_patient(as_priya, storage):
    response = as_priya.post(
        "/api/attachments",
        json={"patient_id": PATIENT_ID, "file_name": "a.jpg", "content_type": "image/jpeg",
              "s3_key": "attachments/someone-else/abc-a.jpg"},
    )
    assert response.status_code == 400
    assert storage["inserted"] == []


def test_register_needs_the_upload_to_have_happened(as_priya, storage):
    storage["exists"] = False
    response = as_priya.post(
        "/api/attachments",
        json={"patient_id": PATIENT_ID, "file_name": "a.jpg", "content_type": "image/jpeg",
              "s3_key": f"attachments/{PATIENT_ID}/abc-a.jpg"},
    )
    assert response.status_code == 400


def test_register_records_the_attachment_with_a_download_link(as_priya, storage):
    key = f"attachments/{PATIENT_ID}/abc-a.jpg"
    response = as_priya.post(
        "/api/attachments",
        json={"patient_id": PATIENT_ID, "file_name": "a.jpg", "content_type": "image/jpeg",
              "s3_key": key},
    )
    assert response.status_code == 200
    assert response.json()["attachment"]["url"] == f"https://s3/get/{key}"
    assert storage["inserted"][0]["uploaded_by"] == PRIYA["id"]
