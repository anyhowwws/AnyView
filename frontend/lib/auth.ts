"use client";

import { useEffect, useState } from "react";
import {
  getRedirectResult,
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut as firebaseSignOut,
} from "firebase/auth";
import { firebaseAuth, firebaseConfigured, googleProvider } from "@/lib/firebase";

/** What the app needs from a signed-in user. Firebase's User satisfies it. */
export interface AuthUser {
  email: string | null;
}

export interface AuthState {
  /** undefined while Firebase is still deciding; null when signed out. */
  user: AuthUser | null | undefined;
  configured: boolean;
}

// Dev only: `NEXT_PUBLIC_FAKE_AUTH=<email>` at build time signs that email in
// without Google. The API accepts it only when it runs on the fake model.
const FAKE_EMAIL = process.env.NEXT_PUBLIC_FAKE_AUTH ?? "";

/** Subscribes to Firebase's auth state. One subscription for the app. */
export function useAuth(): AuthState {
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined);

  useEffect(() => {
    if (FAKE_EMAIL) {
      setUser({ email: FAKE_EMAIL });
      return;
    }
    if (!firebaseConfigured) {
      setUser(null);
      return;
    }
    const auth = firebaseAuth();
    // If we came back from a redirect sign-in, this resolves it; errors here
    // surface through onAuthStateChanged staying null, which the UI handles.
    void getRedirectResult(auth).catch(() => undefined);
    return onAuthStateChanged(auth, setUser);
  }, []);

  return { user, configured: firebaseConfigured || Boolean(FAKE_EMAIL) };
}

/** Popup first (keeps the page), redirect when the popup is blocked. */
export async function signInWithGoogle(): Promise<void> {
  const auth = firebaseAuth();
  try {
    await signInWithPopup(auth, googleProvider);
  } catch (err) {
    const code = (err as { code?: string }).code ?? "";
    if (code === "auth/popup-blocked" || code === "auth/operation-not-supported-in-this-environment") {
      await signInWithRedirect(auth, googleProvider);
      return;
    }
    if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request") {
      return; // the person changed their mind; nothing to report
    }
    throw err;
  }
}

export function signOut(): Promise<void> {
  if (FAKE_EMAIL) return Promise.resolve();
  return firebaseSignOut(firebaseAuth());
}

/** The bearer token for API calls, refreshed by Firebase as needed. */
export async function idToken(): Promise<string | null> {
  if (FAKE_EMAIL) return `fake:${FAKE_EMAIL}`;
  const user = firebaseAuth().currentUser;
  return user ? user.getIdToken() : null;
}
