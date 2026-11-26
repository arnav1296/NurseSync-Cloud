import { motion } from "framer-motion";
import { BedDouble, ChevronRight, UserPlus } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  admitPatient,
  apiErrorMessage,
  assignPatient,
  dischargePatient,
  listAllPatients,
  listStaff,
} from "../api/client";
import type { AdminPatient, AdminStaff, AdmitPatientRequest } from "../api/types";
import BottomSheet from "../components/BottomSheet";
import SegmentedTabs from "../components/SegmentedTabs";
import { fadeUp } from "../lib/motion";

type Tab = "admitted" | "discharged";

const TABS: Array<{ value: Tab; label: string }> = [
  { value: "admitted", label: "Admitted" },
  { value: "discharged", label: "Discharged" },
];

const EMPTY_ADMIT: AdmitPatientRequest = {
  mrn: "",
  full_name: "",
  ward: "",
  bed: "",
  nurse_id: "",
  doctor_id: "",
};

const formatDate = (iso: string | null) =>
  iso
    ? new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : "—";

export default function AdminPatientsView() {
  const [tab, setTab] = useState<Tab>("admitted");
  const [patients, setPatients] = useState<AdminPatient[]>([]);
  const [staff, setStaff] = useState<AdminStaff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [selected, setSelected] = useState<AdminPatient | null>(null);
  const [nurseId, setNurseId] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [confirmDischarge, setConfirmDischarge] = useState(false);
  const [sheetError, setSheetError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [admitting, setAdmitting] = useState(false);
  const [admitForm, setAdmitForm] = useState<AdmitPatientRequest>(EMPTY_ADMIT);
  const [admitError, setAdmitError] = useState<string | null>(null);

  const load = useCallback(async (which: Tab) => {
    setLoading(true);
    try {
      const [{ patients: rows }, { staff: members }] = await Promise.all([
        listAllPatients(which),
        listStaff(),
      ]);
      setPatients(rows);
      setStaff(members);
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't load the patients."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(tab);
  }, [load, tab]);

  const nurses = staff.filter((member) => member.role === "nurse" && member.active);
  const doctors = staff.filter((member) => member.role === "doctor" && member.active);

  function openPatient(patient: AdminPatient) {
    setSelected(patient);
    setNurseId(patient.assigned_nurse_id ?? "");
    setDoctorId(patient.assigned_doctor_id ?? "");
    setConfirmDischarge(false);
    setSheetError(null);
    setSuccess(null);
  }

  function openAdmit() {
    setAdmitForm(EMPTY_ADMIT);
    setAdmitError(null);
    setSuccess(null);
    setAdmitting(true);
  }

  async function onSave() {
    if (!selected) return;
    setBusy(true);
    setSheetError(null);
    try {
      const { changed } = await assignPatient(selected.id, {
        nurse_id: nurseId || undefined,
        doctor_id: doctorId || undefined,
      });
      setSuccess(changed ? `${selected.full_name}'s care team was updated.` : null);
      setSelected(null);
      await load(tab);
    } catch (err) {
      setSheetError(apiErrorMessage(err, "Couldn't save this assignment."));
    } finally {
      setBusy(false);
    }
  }

  async function onDischarge() {
    if (!selected) return;
    // two taps: discharging takes the patient off every nurse and doctor list
    if (!confirmDischarge) {
      setConfirmDischarge(true);
      return;
    }
    setBusy(true);
    setSheetError(null);
    try {
      await dischargePatient(selected.id);
      setSuccess(`${selected.full_name} was discharged.`);
      setSelected(null);
      await load(tab);
    } catch (err) {
      setSheetError(apiErrorMessage(err, "Couldn't discharge this patient."));
      setConfirmDischarge(false);
    } finally {
      setBusy(false);
    }
  }

  async function onAdmit() {
    setBusy(true);
    setAdmitError(null);
    try {
      const { patient } = await admitPatient({
        ...admitForm,
        ward: admitForm.ward?.trim() || null,
        bed: admitForm.bed?.trim() || null,
        doctor_id: admitForm.doctor_id || null,
      });
      setAdmitting(false);
      setSuccess(`${patient.full_name} was admitted.`);
      if (tab === "admitted") {
        await load(tab);
      } else {
        setTab("admitted");
      }
    } catch (err) {
      setAdmitError(apiErrorMessage(err, "Couldn't admit this patient."));
    } finally {
      setBusy(false);
    }
  }

  const canAdmit =
    admitForm.mrn.trim() !== "" && admitForm.full_name.trim() !== "" && admitForm.nurse_id !== "";
  const isHistory = tab === "discharged";

  return (
    <div className="screen-wrapper">
      <header className="screen-header">
        <div>
          <h1 className="screen-title">Patients</h1>
          <p className="screen-subtitle">
            {loading ? "Loading" : `${patients.length} ${isHistory ? "discharged" : "admitted"}`}
          </p>
        </div>
        <button
          type="button"
          className="btn-primary inline-flex items-center gap-1.5"
          onClick={openAdmit}
        >
          <UserPlus size={16} strokeWidth={2.2} />
          Add patient
        </button>
      </header>

      <SegmentedTabs value={tab} onChange={setTab} options={TABS} layoutId="admin-patient-tab" />

      {error && <p className="form-error mt-4">{error}</p>}
      {success && <p className="form-success mt-4">{success}</p>}

      <div className="mt-4">
        {loading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="skeleton-row" />
            ))}
          </div>
        ) : patients.length === 0 && !error ? (
          <div className="empty-state">
            <span className="empty-state-icon">
              <BedDouble size={24} strokeWidth={2.2} />
            </span>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              {isHistory ? "No discharged patients yet" : "No admitted patients"}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {patients.map((patient, index) => (
              <motion.button
                key={patient.id}
                type="button"
                custom={index}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                whileTap={{ scale: 0.99 }}
                className="patient-row"
                style={isHistory ? { opacity: 0.75 } : undefined}
                onClick={() => openPatient(patient)}
              >
                <span className="patient-bed">{patient.bed ?? "—"}</span>
                <span className="min-w-0 flex-1">
                  <p className="patient-name">{patient.full_name}</p>
                  <p className="patient-meta">
                    {patient.mrn}
                    {patient.ward ? ` · ${patient.ward}` : ""}
                  </p>
                  <p className="patient-meta">
                    {isHistory
                      ? `Admitted ${formatDate(patient.admitted_at)} · discharged ${formatDate(patient.discharged_at)}`
                      : `${patient.nurse?.full_name ?? "No nurse"} · ${patient.doctor?.full_name ?? "No doctor"}`}
                  </p>
                </span>
                {isHistory ? (
                  <span className="status-pill">Discharged</span>
                ) : (
                  !patient.assigned_nurse_id && (
                    <span className="status-pill is-pending">Needs nurse</span>
                  )
                )}
                <ChevronRight size={18} strokeWidth={2.2} style={{ color: "var(--text-soft)" }} />
              </motion.button>
            ))}
          </div>
        )}
      </div>

      <BottomSheet
        open={selected !== null}
        title={selected ? `Bed ${selected.bed ?? "—"} · ${selected.full_name}` : ""}
        onClose={() => setSelected(null)}
      >
        {selected && selected.status === "discharged" && (
          <div className="space-y-2">
            <p className="sheet-copy">
              {selected.mrn}
              {selected.ward ? ` · ${selected.ward}` : ""}
            </p>
            <p className="patient-meta">Admitted {formatDate(selected.admitted_at)}</p>
            <p className="patient-meta">Discharged {formatDate(selected.discharged_at)}</p>
            <p className="patient-meta">
              Last care team: {selected.nurse?.full_name ?? "no nurse"} ·{" "}
              {selected.doctor?.full_name ?? "no doctor"}
            </p>
            <p className="patient-meta">
              The record is kept for reference; no new notes, handoffs or alerts can be added.
            </p>
          </div>
        )}

        {selected && selected.status === "admitted" && (
          <div className="space-y-3">
            <div>
              <label className="field-label" htmlFor="assign-nurse">
                Nurse
              </label>
              <select
                id="assign-nurse"
                className="field-input"
                value={nurseId}
                onChange={(event) => setNurseId(event.target.value)}
              >
                <option value="" disabled>
                  Select a nurse…
                </option>
                {nurses.map((nurse) => (
                  <option key={nurse.id} value={nurse.id}>
                    {nurse.full_name}
                    {nurse.on_shift ? " · on shift" : ""}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="assign-doctor">
                Doctor
              </label>
              <select
                id="assign-doctor"
                className="field-input"
                value={doctorId}
                onChange={(event) => setDoctorId(event.target.value)}
              >
                <option value="" disabled>
                  Select a doctor…
                </option>
                {doctors.map((doctor) => (
                  <option key={doctor.id} value={doctor.id}>
                    {doctor.full_name}
                  </option>
                ))}
              </select>
            </div>

            <p className="patient-meta">
              A nurse can't be changed, and the patient can't be discharged, while a handoff
              for this patient is awaiting a response.
            </p>

            {sheetError && <p className="form-error">{sheetError}</p>}

            <button
              type="button"
              className="btn-primary w-full"
              disabled={busy || !nurseId}
              onClick={() => void onSave()}
            >
              {busy && !confirmDischarge ? "Saving…" : "Save assignment"}
            </button>
            <button
              type="button"
              className="btn-danger w-full"
              disabled={busy}
              onClick={() => void onDischarge()}
            >
              {busy && confirmDischarge
                ? "Discharging…"
                : confirmDischarge
                  ? "Tap again to confirm discharge"
                  : "Discharge patient"}
            </button>
          </div>
        )}
      </BottomSheet>

      <BottomSheet open={admitting} title="Add patient" onClose={() => setAdmitting(false)}>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="field-label" htmlFor="admit-mrn">
                MRN
              </label>
              <input
                id="admit-mrn"
                className="field-input"
                value={admitForm.mrn}
                onChange={(event) => setAdmitForm({ ...admitForm, mrn: event.target.value })}
              />
            </div>
            <div>
              <label className="field-label" htmlFor="admit-bed">
                Bed
              </label>
              <input
                id="admit-bed"
                className="field-input"
                placeholder="Optional"
                value={admitForm.bed ?? ""}
                onChange={(event) => setAdmitForm({ ...admitForm, bed: event.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="field-label" htmlFor="admit-name">
              Full name
            </label>
            <input
              id="admit-name"
              className="field-input"
              value={admitForm.full_name}
              onChange={(event) => setAdmitForm({ ...admitForm, full_name: event.target.value })}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="admit-ward">
              Ward
            </label>
            <input
              id="admit-ward"
              className="field-input"
              placeholder="Optional"
              value={admitForm.ward ?? ""}
              onChange={(event) => setAdmitForm({ ...admitForm, ward: event.target.value })}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="admit-nurse">
              Nurse
            </label>
            <select
              id="admit-nurse"
              className="field-input"
              value={admitForm.nurse_id}
              onChange={(event) => setAdmitForm({ ...admitForm, nurse_id: event.target.value })}
            >
              <option value="" disabled>
                Select a nurse…
              </option>
              {nurses.map((nurse) => (
                <option key={nurse.id} value={nurse.id}>
                  {nurse.full_name}
                  {nurse.on_shift ? " · on shift" : ""}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="admit-doctor">
              Doctor
            </label>
            <select
              id="admit-doctor"
              className="field-input"
              value={admitForm.doctor_id ?? ""}
              onChange={(event) => setAdmitForm({ ...admitForm, doctor_id: event.target.value })}
            >
              <option value="">No doctor yet</option>
              {doctors.map((doctor) => (
                <option key={doctor.id} value={doctor.id}>
                  {doctor.full_name}
                </option>
              ))}
            </select>
          </div>

          {admitError && <p className="form-error">{admitError}</p>}

          <button
            type="button"
            className="btn-primary w-full"
            disabled={!canAdmit || busy}
            onClick={() => void onAdmit()}
          >
            {busy ? "Admitting…" : "Admit patient"}
          </button>
        </div>
      </BottomSheet>
    </div>
  );
}
