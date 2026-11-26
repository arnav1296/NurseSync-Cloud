import { BarChart3, BedDouble, LogOut, UserCog } from "lucide-react";
import { Outlet } from "react-router-dom";

import UniversalBottomNav, { type TabDef } from "./components/UniversalBottomNav";
import { ADMIN_OVERVIEW_ROUTE, ADMIN_PATIENTS_ROUTE, ADMIN_STAFF_ROUTE } from "./routes";
import { useAuth } from "./state/AuthContext";

const TABS: TabDef[] = [
  { route: ADMIN_OVERVIEW_ROUTE, label: "Overview", icon: BarChart3 },
  { route: ADMIN_STAFF_ROUTE, label: "Staff", icon: UserCog },
  { route: ADMIN_PATIENTS_ROUTE, label: "Patients", icon: BedDouble },
];

export default function AdminShell() {
  const { staff, signOut } = useAuth();

  return (
    <div className="app-shell">
      <header className="shift-banner">
        <div className="min-w-0">
          <p className="shift-banner-name">{staff?.full_name ?? "…"}</p>
          <p className="shift-banner-meta">{staff?.ward ?? "All wards"} · Administrator</p>
        </div>
        <button
          type="button"
          onClick={() => void signOut()}
          className="shift-banner-signout"
          aria-label="Sign out"
        >
          <LogOut size={16} strokeWidth={2.2} />
        </button>
      </header>

      <div className="app-content">
        <Outlet />
      </div>

      <UniversalBottomNav tabs={TABS} badgeRoute="" badgeCount={0} />
    </div>
  );
}
