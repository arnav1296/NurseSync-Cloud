"""The administrator: accounts, assignments, metrics — and the role boundary."""

import pytest
from fastapi.testclient import TestClient

import main
from routes import admin as admin_routes
from services.auth import get_current_staff
from tests.conftest import ADMIN, ANANYA, DOCTOR_ID, MEHTA, PATIENT_ID, PRIYA, patient

NEW_USER_ID = "66666666-6666-6666-6666-666666666666"

NEW_NURSE = {
    "full_name": "Meera Nair",
    "email": "Meera@Example.test",
    "role": "nurse",
    "ward": "Ward 3B",
    "password": "temporary-pass",
}


@pytest.fixture
def db(monkeypatch):
    state = {
        "staff": {s["id"]: dict(s) for s in (ADMIN, PRIYA, ANANYA, MEHTA)},
        "patient": patient(),
        "pending_for_patient": False,
        "pending_for_nurse": False,
        "existing_email": None,
        "auth_error": None,
        "insert_fails": False,
        "auth_users": [],
        "deleted_auth_users": [],
        "assignments": [],
        "handoffs": [],
        "open_alerts": 0,
        "on_shift": {PRIYA["id"]},
        "discharged": [],
        "admitted": [],
    }

    async def get_staff(staff_id):
        return state["staff"].get(staff_id)

    async def list_all_staff():
        return [dict(s) for s in state["staff"].values()]

    async def get_staff_by_email(email):
        return {"id": "x"} if email == state["existing_email"] else None

    async def create_auth_user(email, password, role):
        if state["auth_error"]:
            raise Exception(state["auth_error"])
        state["auth_users"].append((email, role))
        return "cognito-sub-1"

    async def delete_auth_user(email):
        state["deleted_auth_users"].append(email)

    async def insert_staff(row):
        if state["insert_fails"]:
            raise Exception("insert failed")
        row = {**row, "id": NEW_USER_ID}
        state["staff"][NEW_USER_ID] = row
        return row

    async def set_staff_active(staff_id, active):
        state["staff"][staff_id]["active"] = active
        return state["staff"][staff_id]

    async def list_admitted_patients():
        return [state["patient"]]

    async def get_patient(patient_id):
        return state["patient"] if patient_id == PATIENT_ID else None

    async def list_patients_for_nurse(nurse_id):
        p = state["patient"]
        return [p] if p["assigned_nurse_id"] == nurse_id else []

    async def list_patients_for_doctor(doctor_id):
        p = state["patient"]
        return [p] if p["assigned_doctor_id"] == doctor_id else []

    async def has_pending_handoff(patient_id):
        return state["pending_for_patient"]

    async def has_pending_handoffs_involving(nurse_id):
        return state["pending_for_nurse"]

    async def update_patient_assignment(patient_id, fields):
        state["assignments"].append(fields)
        state["patient"] = {**state["patient"], **fields}
        return state["patient"]

    async def list_handoff_timings():
        return state["handoffs"]

    async def count_open_alerts():
        return state["open_alerts"]

    async def nurses_on_shift():
        return state["on_shift"]

    async def list_patients_by_status(status="admitted"):
        p = state["patient"]
        return [p] if p["status"] == status else []

    async def get_patient_by_mrn(mrn):
        return {"id": PATIENT_ID} if mrn == state["patient"]["mrn"] else None

    async def insert_patient(row):
        state["admitted"].append(row)
        return {**row, "id": "new-patient"}

    async def discharge_patient(patient_id):
        if state["patient"]["status"] != "admitted":
            return {}
        state["discharged"].append(patient_id)
        state["patient"] = {**state["patient"], "status": "discharged"}
        return state["patient"]

    for name, fn in locals().copy().items():
        if callable(fn) and hasattr(admin_routes, name):
            monkeypatch.setattr(admin_routes, name, fn)
    return state


# ---------------------------------------------------------------- role boundary

@pytest.mark.parametrize("who", [PRIYA, MEHTA])
def test_non_admins_are_refused(who, db):
    main.app.dependency_overrides[get_current_staff] = lambda: who
    with TestClient(main.app) as client:
        for path in ("/api/admin/staff", "/api/admin/patients", "/api/admin/metrics"):
            assert client.get(path).status_code == 403
    main.app.dependency_overrides.clear()


# ---------------------------------------------------------------- accounts

def test_lists_staff_with_patient_counts(as_admin, db):
    rows = {s["id"]: s for s in as_admin.get("/api/admin/staff").json()["staff"]}
    assert rows[PRIYA["id"]]["patient_count"] == 1
    assert rows[DOCTOR_ID]["patient_count"] == 1
    assert rows[ANANYA["id"]]["patient_count"] == 0


def test_staff_list_shows_who_is_on_shift(as_admin, db):
    rows = {s["id"]: s for s in as_admin.get("/api/admin/staff").json()["staff"]}
    assert rows[PRIYA["id"]]["on_shift"] is True
    assert rows[ANANYA["id"]]["on_shift"] is False


def test_creates_login_and_roster_row(as_admin, db):
    response = as_admin.post("/api/admin/staff", json=NEW_NURSE)
    assert response.status_code == 200
    # Cognito login in the role's group, and the roster row linked by its sub
    assert db["auth_users"] == [("meera@example.test", "nurse")]
    row = db["staff"][NEW_USER_ID]
    assert row["email"] == "meera@example.test"
    assert row["auth_sub"] == "cognito-sub-1"
    assert row["role"] == "nurse" and row["active"] is True


def test_admin_cannot_create_another_admin(as_admin, db):
    response = as_admin.post("/api/admin/staff", json={**NEW_NURSE, "role": "admin"})
    assert response.status_code == 422
    assert db["auth_users"] == []


def test_short_password_is_refused(as_admin, db):
    response = as_admin.post("/api/admin/staff", json={**NEW_NURSE, "password": "short"})
    assert response.status_code == 422
    assert db["auth_users"] == []


def test_duplicate_roster_email_conflicts(as_admin, db):
    db["existing_email"] = "meera@example.test"
    assert as_admin.post("/api/admin/staff", json=NEW_NURSE).status_code == 409
    assert db["auth_users"] == []


def test_existing_login_email_conflicts(as_admin, db):
    db["auth_error"] = "An error occurred (UsernameExistsException): User already exists"
    assert as_admin.post("/api/admin/staff", json=NEW_NURSE).status_code == 409


def test_weak_password_rejected_by_cognito(as_admin, db):
    db["auth_error"] = "An error occurred (InvalidPasswordException): Password did not conform"
    assert as_admin.post("/api/admin/staff", json=NEW_NURSE).status_code == 400


def test_failed_roster_insert_removes_the_login(as_admin, db):
    db["insert_fails"] = True
    assert as_admin.post("/api/admin/staff", json=NEW_NURSE).status_code == 500
    assert db["deleted_auth_users"] == ["meera@example.test"]


def test_cannot_deactivate_yourself(as_admin, db):
    assert as_admin.post(f"/api/admin/staff/{ADMIN['id']}/deactivate").status_code == 400
    assert db["staff"][ADMIN["id"]]["active"] is True


def test_cannot_deactivate_nurse_who_still_has_patients(as_admin, db):
    response = as_admin.post(f"/api/admin/staff/{PRIYA['id']}/deactivate")
    assert response.status_code == 409
    assert response.json()["detail"]["patients"][0]["id"] == PATIENT_ID
    assert db["staff"][PRIYA["id"]]["active"] is True


def test_cannot_deactivate_doctor_who_still_has_patients(as_admin, db):
    assert as_admin.post(f"/api/admin/staff/{DOCTOR_ID}/deactivate").status_code == 409


def test_cannot_deactivate_nurse_with_pending_handoff(as_admin, db):
    db["pending_for_nurse"] = True
    response = as_admin.post(f"/api/admin/staff/{ANANYA['id']}/deactivate")
    assert response.status_code == 409
    assert db["staff"][ANANYA["id"]]["active"] is True


def test_deactivate_then_reactivate(as_admin, db):
    assert as_admin.post(f"/api/admin/staff/{ANANYA['id']}/deactivate").status_code == 200
    assert db["staff"][ANANYA["id"]]["active"] is False
    assert as_admin.post(f"/api/admin/staff/{ANANYA['id']}/deactivate").status_code == 409
    assert as_admin.post(f"/api/admin/staff/{ANANYA['id']}/reactivate").status_code == 200
    assert db["staff"][ANANYA["id"]]["active"] is True


# ---------------------------------------------------------------- assignment

def test_reassigns_nurse(as_admin, db):
    response = as_admin.patch(
        f"/api/admin/patients/{PATIENT_ID}", json={"nurse_id": ANANYA["id"]}
    )
    assert response.status_code == 200
    assert db["assignments"] == [{"assigned_nurse_id": ANANYA["id"]}]


def test_cannot_assign_a_doctor_as_nurse(as_admin, db):
    response = as_admin.patch(
        f"/api/admin/patients/{PATIENT_ID}", json={"nurse_id": DOCTOR_ID}
    )
    assert response.status_code == 400
    assert db["assignments"] == []


def test_cannot_assign_an_inactive_nurse(as_admin, db):
    db["staff"][ANANYA["id"]]["active"] = False
    response = as_admin.patch(
        f"/api/admin/patients/{PATIENT_ID}", json={"nurse_id": ANANYA["id"]}
    )
    assert response.status_code == 400


def test_cannot_reassign_nurse_during_pending_handoff(as_admin, db):
    db["pending_for_patient"] = True
    response = as_admin.patch(
        f"/api/admin/patients/{PATIENT_ID}", json={"nurse_id": ANANYA["id"]}
    )
    assert response.status_code == 409
    assert db["assignments"] == []


def test_unchanged_assignment_writes_nothing(as_admin, db):
    response = as_admin.patch(
        f"/api/admin/patients/{PATIENT_ID}",
        json={"nurse_id": PRIYA["id"], "doctor_id": DOCTOR_ID},
    )
    assert response.json()["changed"] is False
    assert db["assignments"] == []


def test_unknown_patient_is_404(as_admin, db):
    response = as_admin.patch("/api/admin/patients/nope", json={"nurse_id": ANANYA["id"]})
    assert response.status_code == 404


# ---------------------------------------------------------------- admit and discharge

NEW_PATIENT = {
    "mrn": "mrn-0042",
    "full_name": "Kabir Shah",
    "ward": "Ward 3B",
    "bed": "14",
    "nurse_id": ANANYA["id"],
    "doctor_id": DOCTOR_ID,
}


def test_admits_patient_with_care_team(as_admin, db):
    response = as_admin.post("/api/admin/patients", json=NEW_PATIENT)
    assert response.status_code == 200
    row = db["admitted"][0]
    assert row["mrn"] == "MRN-0042"
    assert row["assigned_nurse_id"] == ANANYA["id"]
    assert row["status"] == "admitted"


def test_admit_refuses_duplicate_mrn(as_admin, db):
    response = as_admin.post("/api/admin/patients", json={**NEW_PATIENT, "mrn": "MRN-0001"})
    assert response.status_code == 409
    assert db["admitted"] == []


def test_admit_requires_an_active_nurse(as_admin, db):
    response = as_admin.post("/api/admin/patients", json={**NEW_PATIENT, "nurse_id": DOCTOR_ID})
    assert response.status_code == 400
    assert db["admitted"] == []


def test_discharges_patient(as_admin, db):
    assert as_admin.post(f"/api/admin/patients/{PATIENT_ID}/discharge").status_code == 200
    assert db["discharged"] == [PATIENT_ID]


def test_cannot_discharge_during_pending_handoff(as_admin, db):
    db["pending_for_patient"] = True
    response = as_admin.post(f"/api/admin/patients/{PATIENT_ID}/discharge")
    assert response.status_code == 409
    assert db["discharged"] == []


def test_cannot_discharge_twice_or_reassign_after(as_admin, db):
    as_admin.post(f"/api/admin/patients/{PATIENT_ID}/discharge")
    assert as_admin.post(f"/api/admin/patients/{PATIENT_ID}/discharge").status_code == 409
    response = as_admin.patch(
        f"/api/admin/patients/{PATIENT_ID}", json={"nurse_id": ANANYA["id"]}
    )
    assert response.status_code == 409


def test_discharged_patients_listed_separately(as_admin, db):
    as_admin.post(f"/api/admin/patients/{PATIENT_ID}/discharge")
    assert as_admin.get("/api/admin/patients").json()["count"] == 0
    history = as_admin.get("/api/admin/patients?status=discharged").json()
    assert history["patients"][0]["id"] == PATIENT_ID


# ---------------------------------------------------------------- metrics

def test_metrics_with_no_handoffs_are_empty_not_errors(as_admin, db):
    body = as_admin.get("/api/admin/metrics").json()
    assert body["handoffs_total"] == 0
    assert body["avg_tta_minutes"] is None
    assert body["clean_accept_rate"] is None


def test_metrics_tta_and_clean_accept_rate(as_admin, db):
    sent = "2026-09-08T14:00:00+00:00"
    db["handoffs"] = [
        {"status": "accepted", "sent_at": sent, "responded_at": "2026-09-08T14:10:00+00:00"},
        {"status": "accepted", "sent_at": sent, "responded_at": "2026-09-08T14:20:00+00:00"},
        {"status": "declined", "sent_at": sent, "responded_at": "2026-09-08T14:30:00+00:00"},
        {"status": "issue_reported", "sent_at": sent, "responded_at": "2026-09-08T15:20:00+00:00"},
        {"status": "pending", "sent_at": sent, "responded_at": None},
    ]
    db["open_alerts"] = 2

    body = as_admin.get("/api/admin/metrics").json()
    assert body["handoffs_total"] == 5
    assert body["responded"] == 4
    assert body["by_status"]["pending"] == 1
    assert body["avg_tta_minutes"] == 35.0
    assert body["median_tta_minutes"] == 25.0
    assert body["clean_accept_rate"] == 0.5
    assert body["open_alerts"] == 2
    assert body["nurses_on_shift"] == 1
    assert body["nurses_active"] == 2
