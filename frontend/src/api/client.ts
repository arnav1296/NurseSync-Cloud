import axios, { AxiosError } from "axios";

import { accessToken, signOut } from "../lib/auth";
import type {
  AdminMetrics,
  AdminPatient,
  AdminStaff,
  AdmitPatientRequest,
  Alert,
  Attachment,
  CorrectNoteResponse,
  CreateNoteRequest,
  CreateStaffRequest,
  DoctorAlertsResponse,
  DoctorPatient,
  DoctorPatientDetailResponse,
  Handoff,
  HandoffDetailResponse,
  HandoffDraft,
  HandoffListResponse,
  MeResponse,
  MyPatientsResponse,
  NoteSection,
  NotesResponse,
  PatientDetailResponse,
  PatientNote,
  SendHandoffRequest,
  Shift,
  StaffRef,
  TranscribeResponse,
  VoiceLanguage,
} from "./types";

// In the cloud, CloudFront serves the site and the API from one origin, so the
// build leaves this empty and calls go to /api on the same host.
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const api = axios.create({ baseURL: API_BASE_URL });

// Identity travels in the Cognito access token, never in a request body: the
// server decides who you are, and the client cannot claim to be another nurse.
api.interceptors.request.use(async (config) => {
  const token = await accessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      // the session is gone or expired; RequireAuth will bounce to /login
      await signOut();
    }
    return Promise.reject(error);
  },
);

/** Pulls the human-readable message out of a FastAPI error response. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      return String((detail as { message: unknown }).message);
    }
  }
  return fallback;
}

// ---------------------------------------------------------------- staff

export async function getMe(): Promise<MeResponse> {
  const { data } = await api.get<MeResponse>("/api/staff/me");
  return data;
}

export async function listNurses(): Promise<{ nurses: StaffRef[] }> {
  const { data } = await api.get<{ nurses: StaffRef[] }>("/api/staff/nurses");
  return data;
}

// ---------------------------------------------------------------- shifts

export async function getCurrentShift(): Promise<{ shift: Shift; created: boolean }> {
  const { data } = await api.get<{ shift: Shift; created: boolean }>(
    "/api/shifts/current",
  );
  return data;
}

export async function endShift(): Promise<{ shift: Shift; message: string }> {
  const { data } = await api.post<{ shift: Shift; message: string }>(
    "/api/shifts/end",
  );
  return data;
}

// ---------------------------------------------------------------- patients

export async function listMyPatients(): Promise<MyPatientsResponse> {
  const { data } = await api.get<MyPatientsResponse>("/api/patients/mine");
  return data;
}

export async function getPatient(patientId: string): Promise<PatientDetailResponse> {
  const { data } = await api.get<PatientDetailResponse>(`/api/patients/${patientId}`);
  return data;
}

// ---------------------------------------------------------------- notes

export async function listNotes(
  patientId: string,
  section?: NoteSection,
): Promise<NotesResponse> {
  const { data } = await api.get<NotesResponse>(`/api/notes/patient/${patientId}`, {
    params: section ? { section } : undefined,
  });
  return data;
}

/** Voice -> draft. Deliberately does not persist; the nurse reviews first. */
export async function transcribeNote(params: {
  audio: Blob;
  patientId: string;
  language: VoiceLanguage;
}): Promise<TranscribeResponse> {
  const formData = new FormData();
  formData.append("audio", params.audio, "recording.wav");
  formData.append("patient_id", params.patientId);
  formData.append("language", params.language);

  const { data } = await api.post<TranscribeResponse>(
    "/api/notes/transcribe",
    formData,
  );
  return data;
}

/** The Fix spelling button: a suggestion, not a save. */
export async function correctNote(
  patientId: string,
  text: string,
): Promise<CorrectNoteResponse> {
  const { data } = await api.post<CorrectNoteResponse>("/api/notes/correct", {
    patient_id: patientId,
    text,
  });
  return data;
}

export async function createNote(
  payload: CreateNoteRequest,
): Promise<{ note: PatientNote }> {
  const { data } = await api.post<{ note: PatientNote }>("/api/notes", payload);
  return data;
}

// ---------------------------------------------------------------- handoff

export async function draftHandoff(
  patientIds: string[],
): Promise<{ drafts: HandoffDraft[] }> {
  const { data } = await api.post<{ drafts: HandoffDraft[] }>("/api/handoff/draft", {
    patient_ids: patientIds,
  });
  return data;
}

export async function sendHandoff(
  payload: SendHandoffRequest,
): Promise<{ handoffs: Handoff[]; count: number; sent_to: string }> {
  const { data } = await api.post("/api/handoff/send", payload);
  return data;
}

export async function getInbox(): Promise<HandoffListResponse> {
  const { data } = await api.get<HandoffListResponse>("/api/handoff/inbox");
  return data;
}

export async function getSentHandoffs(): Promise<HandoffListResponse> {
  const { data } = await api.get<HandoffListResponse>("/api/handoff/sent");
  return data;
}

export async function getHandoff(handoffId: string): Promise<HandoffDetailResponse> {
  const { data } = await api.get<HandoffDetailResponse>(`/api/handoff/${handoffId}`);
  return data;
}

export async function acceptHandoff(handoffId: string) {
  const { data } = await api.post(`/api/handoff/${handoffId}/accept`);
  return data;
}

export async function declineHandoff(handoffId: string, note: string) {
  const { data } = await api.post(`/api/handoff/${handoffId}/decline`, { note });
  return data;
}

export async function reportHandoffIssue(handoffId: string, note: string) {
  const { data } = await api.post(`/api/handoff/${handoffId}/report-issue`, { note });
  return data;
}

// ---------------------------------------------------------------- alerts

export async function raiseAlert(
  patientId: string,
  message: string,
): Promise<{ alert: Alert; sent_to: string }> {
  const { data } = await api.post<{ alert: Alert; sent_to: string }>("/api/alerts", {
    patient_id: patientId,
    message,
  });
  return data;
}

export async function listPatientAlerts(patientId: string): Promise<{ alerts: Alert[] }> {
  const { data } = await api.get<{ alerts: Alert[] }>(`/api/alerts/patient/${patientId}`);
  return data;
}

// ---------------------------------------------------------------- doctor

export async function listDoctorPatients(): Promise<{ patients: DoctorPatient[] }> {
  const { data } = await api.get<{ patients: DoctorPatient[] }>("/api/doctor/patients");
  return data;
}

export async function getDoctorPatient(
  patientId: string,
): Promise<DoctorPatientDetailResponse> {
  const { data } = await api.get<DoctorPatientDetailResponse>(
    `/api/doctor/patients/${patientId}`,
  );
  return data;
}

export async function getDoctorAlerts(): Promise<DoctorAlertsResponse> {
  const { data } = await api.get<DoctorAlertsResponse>("/api/doctor/alerts");
  return data;
}

export async function acknowledgeAlert(alertId: string): Promise<{ alert: Alert }> {
  const { data } = await api.post<{ alert: Alert }>(
    `/api/doctor/alerts/${alertId}/acknowledge`,
  );
  return data;
}

// ---------------------------------------------------------------- admin

export async function listStaff(): Promise<{ staff: AdminStaff[] }> {
  const { data } = await api.get<{ staff: AdminStaff[] }>("/api/admin/staff");
  return data;
}

export async function createStaff(
  payload: CreateStaffRequest,
): Promise<{ staff: AdminStaff }> {
  const { data } = await api.post<{ staff: AdminStaff }>("/api/admin/staff", payload);
  return data;
}

export async function setStaffActive(staffId: string, active: boolean) {
  const action = active ? "reactivate" : "deactivate";
  const { data } = await api.post(`/api/admin/staff/${staffId}/${action}`);
  return data;
}

export async function listAllPatients(
  status: "admitted" | "discharged" = "admitted",
): Promise<{ patients: AdminPatient[] }> {
  const { data } = await api.get<{ patients: AdminPatient[] }>("/api/admin/patients", {
    params: { status },
  });
  return data;
}

export async function admitPatient(
  payload: AdmitPatientRequest,
): Promise<{ patient: AdminPatient }> {
  const { data } = await api.post<{ patient: AdminPatient }>("/api/admin/patients", payload);
  return data;
}

export async function dischargePatient(patientId: string): Promise<{ patient: AdminPatient }> {
  const { data } = await api.post<{ patient: AdminPatient }>(
    `/api/admin/patients/${patientId}/discharge`,
  );
  return data;
}

export async function assignPatient(
  patientId: string,
  payload: { nurse_id?: string; doctor_id?: string },
): Promise<{ patient: AdminPatient; changed: boolean }> {
  const { data } = await api.patch<{ patient: AdminPatient; changed: boolean }>(
    `/api/admin/patients/${patientId}`,
    payload,
  );
  return data;
}

export async function getAdminMetrics(): Promise<AdminMetrics> {
  const { data } = await api.get<AdminMetrics>("/api/admin/metrics");
  return data;
}

/** The patients named in a 409 that blocks an action until they're reassigned. */
// ---------------------------------------------------------------- attachments (Amazon S3)

/** Upload a photo or PDF: get a presigned URL, PUT the file to S3, then register it. */
export async function uploadAttachment(patientId: string, file: File): Promise<Attachment> {
  const { data: slot } = await api.post<{ upload_url: string; s3_key: string }>(
    "/api/attachments/upload-url",
    { patient_id: patientId, file_name: file.name, content_type: file.type },
  );
  // straight to S3: no API token on this request, the URL itself is the permission
  const put = await fetch(slot.upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!put.ok) throw new Error("The upload to storage failed.");
  const { data } = await api.post<{ attachment: Attachment }>("/api/attachments", {
    patient_id: patientId,
    file_name: file.name,
    content_type: file.type,
    s3_key: slot.s3_key,
  });
  return data.attachment;
}

export async function listAttachments(patientId: string): Promise<{ attachments: Attachment[] }> {
  const { data } = await api.get<{ attachments: Attachment[] }>(
    `/api/attachments/patient/${patientId}`,
  );
  return data;
}

export async function listDoctorAttachments(
  patientId: string,
): Promise<{ attachments: Attachment[] }> {
  const { data } = await api.get<{ attachments: Attachment[] }>(
    `/api/attachments/doctor/patient/${patientId}`,
  );
  return data;
}

export function blockingPatients(
  error: unknown,
): Array<{ id: string; full_name: string; bed: string | null }> {
  if (!axios.isAxiosError(error)) return [];
  const detail = (error.response?.data as { detail?: { patients?: unknown } } | undefined)
    ?.detail;
  return Array.isArray(detail?.patients) ? detail.patients : [];
}
