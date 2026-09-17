"use client";

import { useEffect, useState } from "react";
import {
  getRedirectResult,
  onAuthStateChanged,
  signInWithPopup,
  signInWithRedirect,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { firebaseAuth, firebaseConfigured, googleProvider } from "@/lib/firebase";

export interface AuthState {
  /** undefined while Firebase is still deciding; null when signed out. */
  user: User | null | undefined;
  configured: boolean;
}

/** Subscribes to Firebase's auth state. One subscription for the app. */
export function useAuth(): AuthState {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
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

  return { user, configured: firebaseConfigured };
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
  return firebaseSignOut(firebaseAuth());
}

/** The bearer token for API calls, refreshed by Firebase as needed. */
export async function idToken(): Promise<string | null> {
  const user = firebaseAuth().currentUser;
  return user ? user.getIdToken() : null;
}
