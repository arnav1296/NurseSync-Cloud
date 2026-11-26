export type StaffRole = "nurse" | "doctor" | "admin";
export type NoteSection = "detail" | "major_decision";
export type NoteSource = "voice" | "typed";
export type VoiceLanguage = "en" | "hi";
export type HandoffStatus = "pending" | "accepted" | "declined" | "issue_reported";

export interface Staff {
  id: string;
  full_name: string;
  email: string;
  role: StaffRole;
  ward: string | null;
  active: boolean;
}

/** Trimmed staff shape returned as a nested relation. */
export interface StaffRef {
  id: string;
  full_name: string;
}

export interface Shift {
  id: string;
  nurse_id: string;
  started_at: string;
  ended_at: string | null;
  status: "active" | "closed";
}

export interface MeResponse {
  staff: Staff;
  active_shift: Shift | null;
}

export interface Patient {
  id: string;
  mrn: string;
  full_name: string;
  ward: string | null;
  bed: string | null;
  status: "admitted" | "discharged";
  admitted_at: string;
  discharged_at: string | null;
  assigned_nurse_id: string | null;
  assigned_doctor_id: string | null;
}

/** Patient plus the per-patient counters the My Patients list shows. */
export interface AssignedPatient extends Patient {
  note_count: number;
  last_note_at: string | null;
}

export interface MyPatientsResponse {
  patients: AssignedPatient[];
  count: number;
}

export interface PatientDetailResponse {
  patient: Patient;
  doctor: StaffRef | null;
  is_mine: boolean;
}

export interface PatientNote {
  id: string;
  patient_id: string;
  author_id: string;
  shift_id: string | null;
  section: NoteSection;
  body: string;
  source: NoteSource;
  raw_transcript: string | null;
  stt_confidence: number | null;
  created_at: string;
  author?: StaffRef | null;
}

export interface NotesResponse {
  notes: PatientNote[];
  count: number;
}

export interface CreateNoteRequest {
  patient_id: string;
  section: NoteSection;
  body: string;
  source?: NoteSource;
  raw_transcript?: string | null;
  stt_confidence?: number | null;
}

/** The draft from POST /api/notes/transcribe. Nothing is saved yet. */
export interface TranscribeResponse {
  raw_transcript: string;
  corrected: string;
  suggested_section: NoteSection;
  /** null when the provider gives no usable score. */
  confidence: number | null;
  low_confidence: boolean;
  saved: false;
}

export interface CorrectNoteResponse {
  corrected: string;
  changed: boolean;
}

/** Summarised from the nurse's notes this shift; she edits before sending. */
export interface HandoffDraft {
  patient: Pick<Patient, "id" | "full_name" | "bed" | "mrn">;
  details: string;
  major_decisions: string;
  /** false means the fields are her notes as written. */
  ai_generated: boolean;
  source_details: string;
  source_major_decisions: string;
  note_count: number;
}

export interface Handoff {
  id: string;
  patient_id: string;
  from_nurse_id: string;
  to_nurse_id: string;
  from_shift_id: string | null;
  details: string | null;
  major_decisions: string | null;
  status: HandoffStatus;
  response_note: string | null;
  sent_at: string;
  responded_at: string | null;
  patient?: Pick<Patient, "id" | "full_name" | "mrn" | "ward" | "bed"> | null;
  from_nurse?: StaffRef | null;
  to_nurse?: StaffRef | null;
}

export interface HandoffEvent {
  id: string;
  handoff_id: string;
  actor_id: string;
  event: "sent" | "viewed" | "accepted" | "declined" | "issue_reported";
  note: string | null;
  created_at: string;
  actor?: StaffRef | null;
}

export interface HandoffDetailResponse {
  handoff: Handoff;
  notes: PatientNote[];
  events: HandoffEvent[];
}

export interface HandoffListResponse {
  handoffs: Handoff[];
  count: number;
}

export interface Alert {
  id: string;
  patient_id: string;
  raised_by: string;
  doctor_id: string;
  message: string | null;
  status: "open" | "acknowledged" | "resolved";
  created_at: string;
  acknowledged_at: string | null;
  patient?: Pick<Patient, "id" | "full_name" | "mrn" | "ward" | "bed"> | null;
  raised_by_staff?: StaffRef | null;
  doctor?: StaffRef | null;
}

export interface DoctorAlertsResponse {
  open: Alert[];
  acknowledged: Alert[];
  open_count: number;
}

export interface DoctorPatient extends AssignedPatient {
  nurse?: StaffRef | null;
  open_alert_count: number;
}

export interface DoctorPatientDetailResponse {
  patient: Patient;
  nurse: StaffRef | null;
  notes: PatientNote[];
  alerts: Alert[];
}

export interface AdminStaff extends Staff {
  patient_count: number;
  /** Nurses only: an open shift, which starts at sign-in and ends with End shift. */
  on_shift: boolean;
}

export interface AdmitPatientRequest {
  mrn: string;
  full_name: string;
  ward: string | null;
  bed: string | null;
  nurse_id: string;
  doctor_id: string | null;
}

export interface CreateStaffRequest {
  full_name: string;
  email: string;
  role: "nurse" | "doctor";
  ward: string | null;
  password: string;
}

export interface AdminPatient extends Patient {
  nurse?: StaffRef | null;
  doctor?: StaffRef | null;
}

export interface AdminMetrics {
  handoffs_total: number;
  by_status: Record<HandoffStatus, number>;
  responded: number;
  /** null until at least one handoff has been answered. */
  avg_tta_minutes: number | null;
  median_tta_minutes: number | null;
  clean_accept_rate: number | null;
  open_alerts: number;
  nurses_on_shift: number;
  nurses_active: number;
}

/** A photo or PDF on a patient, stored in S3; `url` is a short-lived download link. */
export interface Attachment {
  id: string;
  patient_id: string;
  uploaded_by: string;
  s3_key: string;
  file_name: string;
  content_type: string;
  created_at: string;
  url: string;
  uploader?: StaffRef | null;
}

export interface SendHandoffRequest {
  to_nurse_id: string;
  items: Array<{
    patient_id: string;
    details: string;
    major_decisions: string;
  }>;
}
