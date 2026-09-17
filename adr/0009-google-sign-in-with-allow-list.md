# 0009 — Google sign-in through Identity Platform, allow-listed by email

- **Status:** Accepted
- **Date:** 2026-09-18

## Context

Phase 0 had no users: the Cloud Run service was reachable only by IAM
invokers, which made the deployed site unusable from a browser (ADR 0006).
Phase 1 stores personal career data per user, so identity has to exist
before the first row is written. The brief fixes the provider: Identity
Platform. What it leaves open is the sign-in method, who is allowed in, and
how the API verifies a caller.

The API spends model tokens on every session. Whoever can call it can spend
the budget; the budget alert only alerts.

## Options considered

**Sign-in method.** Google only, or Google plus email/password. Email/password
adds reset flows, email templates, and a second provider to test, for a tool
whose users all have Google accounts.

**Who is allowed in.** Any verified Google account, or an allow-list. Open
sign-up means anyone who finds the URL can run interviews on the owner's
budget.

**Token verification on the API.** The Firebase Admin SDK (a large dependency
tree, most of it for Firestore and Storage we do not use) or `google-auth`'s
`verify_firebase_token`, which is already installed underneath the Vertex SDK.

**Provisioning the Google OAuth client.** Terraform (puts the client secret in
state) or the Firebase CLI from a checked-in provider config (the secret never
leaves Google). AnyTatt used the CLI and it held up.

**The browser API key.** Hand-made in Terraform with narrow API restrictions,
or the key Firebase creates when a web app is registered. AnyTatt made a narrow
key and found it could not load Firebase's hosted sign-in handler; it ended up
copying the CLI-created key around as a GitHub secret.

## Decision

- **Google only**, with `prompt=select_account` so the right account is chosen
  on shared machines.
- **Allow-list by email**, `ALLOWED_EMAILS` on Cloud Run from a Terraform
  variable. Case-insensitive; empty means nobody. The list starts as the owner.
  This is the cost guard, so the Cloud Run invoker can be public again.
- **`google-auth` verifies the ID token** on every `/interview/*` route, with
  the project id as audience so a token from any other Firebase project fails.
  `email_verified` is required. 401 for no/expired token, 403 for a verified
  account that is not on the list; both are sentences the UI shows.
- **Terraform owns** the Identity Platform config, the authorized domains, and
  a `google_firebase_web_app` whose config (api key, project id) is an output
  and a build-time variable. **The Firebase CLI owns** the Google provider,
  provisioned once from `firebase-auth.json`.
- **`authDomain` is the app's own origin** (`anyview.anyapps.cloud`), where
  Hosting serves `/__/auth/handler`, so the redirect flow stays same-origin
  (Safari blocks the cross-origin storage it needs otherwise). Popup first,
  redirect when the popup is blocked.

## What this costs

- **One dependency in the frontend** (`firebase`, sign-in only). None in the
  backend.
- **A one-time owner command** to provision the provider (README). It cannot
  be automated without putting the OAuth client in Terraform state.
- **The web config is public.** It has to be — it ships in the JavaScript. The
  API key identifies the project to Google's sign-in service; it is not a
  credential, and the allow-list is what stands between a stranger and the
  budget.
- **Adding a friend is a tfvars edit and an apply**, not a UI. Fine at this
  scale; a Phase 4 admin surface can replace it.
- **Every API call fetches or refreshes a token.** Firebase caches it for an
  hour; the cost is one header.
