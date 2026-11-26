import { Amplify } from "aws-amplify";
import {
  fetchAuthSession,
  getCurrentUser,
  signIn as cognitoSignIn,
  signOut as cognitoSignOut,
} from "aws-amplify/auth";

const userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID;
const userPoolClientId = import.meta.env.VITE_COGNITO_CLIENT_ID;

if (!userPoolId || !userPoolClientId) {
  throw new Error(
    "Missing VITE_COGNITO_USER_POOL_ID / VITE_COGNITO_CLIENT_ID. Copy frontend/.env.example to frontend/.env.",
  );
}

/**
 * Amazon Cognito handles sign-in only. All patient data goes through the API,
 * which verifies the access token Cognito issues. Amplify stores the session
 * and refreshes tokens on its own.
 */
Amplify.configure({
  Auth: { Cognito: { userPoolId, userPoolClientId, loginWith: { email: true } } },
});

export type AuthUser = { userId: string; username: string };

export async function currentUser(): Promise<AuthUser | null> {
  try {
    const { userId, username } = await getCurrentUser();
    return { userId, username };
  } catch {
    return null;
  }
}

/** The access token for API calls, refreshed if it has expired; null when signed out. */
export async function accessToken(): Promise<string | null> {
  try {
    const session = await fetchAuthSession();
    return session.tokens?.accessToken?.toString() ?? null;
  } catch {
    return null;
  }
}

export async function signIn(email: string, password: string): Promise<void> {
  // a stale session from another account would make Cognito refuse the new sign-in
  if (await currentUser()) await cognitoSignOut();
  const { isSignedIn, nextStep } = await cognitoSignIn({ username: email, password });
  if (!isSignedIn) {
    throw new Error(`Sign-in needs another step (${nextStep.signInStep}). Ask an administrator.`);
  }
}

export async function signOut(): Promise<void> {
  await cognitoSignOut();
}
