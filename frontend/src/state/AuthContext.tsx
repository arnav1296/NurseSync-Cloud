import { Hub } from "aws-amplify/utils";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { getCurrentShift, getMe } from "../api/client";
import type { Shift, Staff } from "../api/types";
import {
  type AuthUser,
  currentUser,
  signIn as cognitoSignIn,
  signOut as cognitoSignOut,
} from "../lib/auth";

type AuthState = {
  /** The signed-in Cognito user, or null. */
  session: AuthUser | null;
  staff: Staff | null;
  shift: Shift | null;
  /** True until the stored session has been checked — render nothing routed until then. */
  loading: boolean;
  profileError: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refreshShift: () => Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<AuthUser | null>(null);
  const [staff, setStaff] = useState<Staff | null>(null);
  const [shift, setShift] = useState<Shift | null>(null);
  const [loading, setLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    currentUser().then((user) => {
      if (!active) return;
      setSession(user);
      setLoading(false);
    });

    // signing out anywhere (the sign-out button, or the API client on a 401) and a
    // refresh token that has expired both land here
    const stop = Hub.listen("auth", ({ payload }) => {
      if (payload.event === "signedOut" || payload.event === "tokenRefresh_failure") {
        setSession(null);
        setStaff(null);
        setShift(null);
        setProfileError(null);
      }
    });

    return () => {
      active = false;
      stop();
    };
  }, []);

  // Once signed in, load the ward profile and open the shift. A nurse who
  // authenticates but has no staff row is signed in to nothing useful, so we
  // surface that rather than dropping her into an empty app.
  useEffect(() => {
    if (!session) return;
    let active = true;

    (async () => {
      try {
        const me = await getMe();
        if (!active) return;
        setStaff(me.staff);
        setProfileError(null);

        if (me.staff.role === "nurse") {
          const current = me.active_shift ?? (await getCurrentShift()).shift;
          if (active) setShift(current);
        }
      } catch {
        if (!active) return;
        setProfileError(
          "Signed in, but no ward profile is linked to this account. Ask an administrator to add you.",
        );
      }
    })();

    return () => {
      active = false;
    };
  }, [session]);

  const signIn = useCallback(async (email: string, password: string) => {
    await cognitoSignIn(email, password);
    setSession(await currentUser());
  }, []);

  const signOut = useCallback(async () => {
    await cognitoSignOut();
  }, []);

  const refreshShift = useCallback(async () => {
    const { shift: next } = await getCurrentShift();
    setShift(next);
  }, []);

  const value = useMemo(
    () => ({
      session,
      staff,
      shift,
      loading,
      profileError,
      signIn,
      signOut,
      refreshShift,
    }),
    [session, staff, shift, loading, profileError, signIn, signOut, refreshShift],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
