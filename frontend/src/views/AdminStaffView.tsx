import { motion } from "framer-motion";
import { UserPlus, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
  apiErrorMessage,
  blockingPatients,
  createStaff,
  listStaff,
  setStaffActive,
} from "../api/client";
import type { AdminStaff, CreateStaffRequest } from "../api/types";
import BottomSheet from "../components/BottomSheet";
import SegmentedTabs from "../components/SegmentedTabs";
import { fadeUp } from "../lib/motion";
import { useAuth } from "../state/AuthContext";

type Tab = "nurse" | "doctor";

const TABS: Array<{ value: Tab; label: string }> = [
  { value: "nurse", label: "Nurses" },
  { value: "doctor", label: "Doctors" },
];

const EMPTY_FORM: CreateStaffRequest = {
  full_name: "",
  email: "",
  role: "nurse",
  ward: "",
  password: "",
};

export default function AdminStaffView() {
  const { staff: me } = useAuth();
  const [tab, setTab] = useState<Tab>("nurse");
  const [staff, setStaff] = useState<AdminStaff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<CreateStaffRequest>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const [selected, setSelected] = useState<AdminStaff | null>(null);
  const [sheetError, setSheetError] = useState<string | null>(null);
  const [blockers, setBlockers] = useState<ReturnType<typeof blockingPatients>>([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { staff: rows } = await listStaff();
      setStaff(rows);
      setError(null);
    } catch (err) {
      setError(apiErrorMessage(err, "Couldn't load the staff list."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = staff.filter((member) => member.role === tab);

  function openAdd() {
    setForm({ ...EMPTY_FORM, role: tab });
    setFormError(null);
    setSuccess(null);
    setAdding(true);
  }

  async function onCreate() {
    setBusy(true);
    setFormError(null);
    try {
      const { staff: created } = await createStaff({
        ...form,
        ward: form.ward?.trim() || null,
      });
      setAdding(false);
      setTab(created.role as Tab);
      setSuccess(`${created.full_name} can now sign in with ${created.email}.`);
      await load();
    } catch (err) {
      setFormError(apiErrorMessage(err, "Couldn't add this person."));
    } finally {
      setBusy(false);
    }
  }

  function openMember(member: AdminStaff) {
    setSelected(member);
    setSheetError(null);
    setBlockers([]);
    setSuccess(null);
  }

  async function onToggleActive() {
    if (!selected) return;
    setBusy(true);
    setSheetError(null);
    setBlockers([]);
    try {
      await setStaffActive(selected.id, !selected.active);
      setSuccess(
        `${selected.full_name} is ${selected.active ? "deactivated" : "active again"}.`,
      );
      setSelected(null);
      await load();
    } catch (err) {
      setSheetError(apiErrorMessage(err, "Couldn't update this account."));
      setBlockers(blockingPatients(err));
    } finally {
      setBusy(false);
    }
  }

  const canCreate =
    form.full_name.trim() !== "" && form.email.includes("@") && form.password.length >= 8;

  return (
    <div className="screen-wrapper">
      <header className="screen-header">
        <div>
          <h1 className="screen-title">Staff</h1>
          <p className="screen-subtitle">
            {loading
              ? "Loading"
              : tab === "nurse"
                ? `${visible.length} nurses · ${visible.filter((n) => n.active && n.on_shift).length} on shift`
                : `${visible.length} doctors`}
          </p>
        </div>
        <button
          type="button"
          className="btn-primary inline-flex items-center gap-1.5"
          onClick={openAdd}
        >
          <UserPlus size={16} strokeWidth={2.2} />
          Add
        </button>
      </header>

      <SegmentedTabs value={tab} onChange={setTab} options={TABS} layoutId="admin-staff-tab" />

      {error && <p className="form-error mt-4">{error}</p>}
      {success && <p className="form-success mt-4">{success}</p>}

      <div className="mt-4">
        {loading ? (
          <div className="space-y-3">
            {[0, 1, 2].map((index) => (
              <div key={index} className="skeleton-row" />
            ))}
          </div>
        ) : visible.length === 0 && !error ? (
          <div className="empty-state">
            <span className="empty-state-icon">
              <Users size={24} strokeWidth={2.2} />
            </span>
            <p className="text-sm font-semibold text-[var(--text-primary)]">
              No {tab === "nurse" ? "nurses" : "doctors"} yet
            </p>
            <p className="max-w-xs text-[0.8rem]">Use Add to create their login.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {visible.map((member, index) => (
              <motion.button
                key={member.id}
                type="button"
                custom={index}
                variants={fadeUp}
                initial="hidden"
                animate="visible"
                whileTap={{ scale: 0.99 }}
                className="patient-row"
                style={member.active ? undefined : { opacity: 0.6 }}
                onClick={() => openMember(member)}
              >
                <span className="patient-bed">
                  {member.full_name
                    .replace(/^Dr\.?\s+/i, "")
                    .split(/\s+/)
                    .map((part) => part[0])
                    .join("")
                    .slice(0, 2)
                    .toUpperCase()}
                </span>
                <span className="min-w-0 flex-1">
                  <p className="patient-name">{member.full_name}</p>
                  <p className="patient-meta truncate">{member.email}</p>
                  <p className="patient-meta">
                    {member.ward ?? "No ward"} · {member.patient_count} patient
                    {member.patient_count === 1 ? "" : "s"}
                  </p>
                </span>
                {!member.active ? (
                  <span className="status-pill is-declined">Inactive</span>
                ) : member.role === "nurse" ? (
                  <span className={member.on_shift ? "status-pill is-accepted" : "status-pill"}>
                    {member.on_shift ? "On shift" : "Off shift"}
                  </span>
                ) : null}
              </motion.button>
            ))}
          </div>
        )}
      </div>

      <BottomSheet open={adding} title="Add staff" onClose={() => setAdding(false)}>
        <div className="space-y-3">
          <div>
            <label className="field-label" htmlFor="staff-role">
              Role
            </label>
            <select
              id="staff-role"
              className="field-input"
              value={form.role}
              onChange={(event) =>
                setForm({ ...form, role: event.target.value as CreateStaffRequest["role"] })
              }
            >
              <option value="nurse">Nurse</option>
              <option value="doctor">Doctor</option>
            </select>
          </div>
          <div>
            <label className="field-label" htmlFor="staff-name">
              Full name
            </label>
            <input
              id="staff-name"
              className="field-input"
              value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="staff-email">
              Email
            </label>
            <input
              id="staff-email"
              type="email"
              autoComplete="off"
              className="field-input"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="staff-ward">
              Ward
            </label>
            <input
              id="staff-ward"
              className="field-input"
              placeholder="Optional"
              value={form.ward ?? ""}
              onChange={(event) => setForm({ ...form, ward: event.target.value })}
            />
          </div>
          <div>
            <label className="field-label" htmlFor="staff-password">
              Temporary password
            </label>
            <input
              id="staff-password"
              type="text"
              autoComplete="new-password"
              className="field-input"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
            />
            <p className="patient-meta mt-1">At least 8 characters. Give it to them in person.</p>
          </div>

          {formError && <p className="form-error">{formError}</p>}

          <button
            type="button"
            className="btn-primary w-full"
            disabled={!canCreate || busy}
            onClick={() => void onCreate()}
          >
            {busy ? "Creating…" : "Create login"}
          </button>
        </div>
      </BottomSheet>

      <BottomSheet
        open={selected !== null}
        title={selected?.full_name ?? ""}
        onClose={() => setSelected(null)}
      >
        {selected && (
          <div className="space-y-3">
            <p className="sheet-copy">
              {selected.email} · {selected.ward ?? "No ward"} · {selected.patient_count} patient
              {selected.patient_count === 1 ? "" : "s"}
              {selected.role === "nurse" && selected.active
                ? selected.on_shift
                  ? " · On shift now"
                  : " · Off shift"
                : ""}
            </p>

            {sheetError && <p className="form-error">{sheetError}</p>}
            {blockers.length > 0 && (
              <ul className="space-y-1">
                {blockers.map((patient) => (
                  <li key={patient.id} className="patient-meta">
                    Bed {patient.bed ?? "—"} · {patient.full_name}
                  </li>
                ))}
              </ul>
            )}

            {selected.id === me?.id ? (
              <p className="patient-meta">This is your own account.</p>
            ) : (
              <button
                type="button"
                className={selected.active ? "btn-danger w-full" : "btn-primary w-full"}
                disabled={busy}
                onClick={() => void onToggleActive()}
              >
                {busy
                  ? "Saving…"
                  : selected.active
                    ? "Deactivate account"
                    : "Reactivate account"}
              </button>
            )}
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
