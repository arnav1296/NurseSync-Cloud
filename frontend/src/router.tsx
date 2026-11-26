import { createHashRouter, Navigate } from "react-router-dom";

import AdminShell from "./AdminShell";
import AppShell from "./App";
import RequireAuth from "./components/RequireAuth";
import RequireRole from "./components/RequireRole";
import Dashboard from "./Dashboard";
import DoctorShell from "./DoctorShell";
import { ADMIN_OVERVIEW_ROUTE, DEFAULT_ROUTE, DOCTOR_PATIENTS_ROUTE } from "./routes";
import AdminOverviewView from "./views/AdminOverviewView";
import AdminPatientsView from "./views/AdminPatientsView";
import AdminStaffView from "./views/AdminStaffView";
import DoctorAlertsView from "./views/DoctorAlertsView";
import DoctorPatientDetailView from "./views/DoctorPatientDetailView";
import DoctorPatientsView from "./views/DoctorPatientsView";
import HandoffReviewView from "./views/HandoffReviewView";
import HandoffView from "./views/HandoffView";
import LoginView from "./views/LoginView";
import MyPatientsView from "./views/MyPatientsView";
import NoteComposerView from "./views/NoteComposerView";
import PatientDetailView from "./views/PatientDetailView";

export const router = createHashRouter([
  {
    path: "/login",
    element: <LoginView />,
  },
  {
    path: "/doctor",
    element: (
      <RequireAuth>
        <RequireRole role="doctor">
          <DoctorShell />
        </RequireRole>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to={DOCTOR_PATIENTS_ROUTE} replace /> },
      { path: "patients", element: <DoctorPatientsView /> },
      { path: "patients/:patientId", element: <DoctorPatientDetailView /> },
      { path: "alerts", element: <DoctorAlertsView /> },
      { path: "*", element: <Navigate to={DOCTOR_PATIENTS_ROUTE} replace /> },
    ],
  },
  {
    path: "/admin",
    element: (
      <RequireAuth>
        <RequireRole role="admin">
          <AdminShell />
        </RequireRole>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to={ADMIN_OVERVIEW_ROUTE} replace /> },
      { path: "overview", element: <AdminOverviewView /> },
      { path: "staff", element: <AdminStaffView /> },
      { path: "patients", element: <AdminPatientsView /> },
      { path: "*", element: <Navigate to={ADMIN_OVERVIEW_ROUTE} replace /> },
    ],
  },
  {
    path: "/",
    element: (
      <RequireAuth>
        <RequireRole role="nurse">
          <AppShell />
        </RequireRole>
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to={DEFAULT_ROUTE} replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "patients", element: <MyPatientsView /> },
      { path: "patients/:patientId", element: <PatientDetailView /> },
      { path: "patients/:patientId/note", element: <NoteComposerView /> },
      { path: "handoff", element: <HandoffView /> },
      { path: "handoff/:handoffId", element: <HandoffReviewView /> },
      { path: "*", element: <Navigate to={DEFAULT_ROUTE} replace /> },
    ],
  },
]);
