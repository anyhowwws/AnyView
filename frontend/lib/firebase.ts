// Firebase client, used only for sign-in (ADR 0009). The three values are the
// project's public web config — they identify the project to Google's sign-in
// service and are not credentials. They come from `terraform output
// firebase_web_config` and are baked in at build time like the API URL.
//
// authDomain is the app's own origin in production: Firebase Hosting serves
// /__/auth/handler on the custom domain, which keeps the sign-in redirect
// same-origin (Safari blocks the cross-origin storage the flow needs
// otherwise). Locally it is the project's firebaseapp.com handler.

import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, type Auth } from "firebase/auth";

const config = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
};

export const firebaseConfigured = Boolean(config.apiKey && config.authDomain && config.projectId);

let app: FirebaseApp | undefined;

export function firebaseAuth(): Auth {
  if (!app) app = getApps()[0] ?? initializeApp(config);
  return getAuth(app);
}

export const googleProvider = new GoogleAuthProvider();
// Ask for the minimum: Google's basic profile gives us a verified email and a uid.
googleProvider.setCustomParameters({ prompt: "select_account" });
