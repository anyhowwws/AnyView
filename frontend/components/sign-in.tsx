"use client";

import { useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { signInWithGoogle } from "@/lib/auth";

interface Props {
  configured: boolean;
}

/** The gate. One button; the disclosure says what signing in is for. */
export function SignIn({ configured }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="workspace-panel mx-auto mt-12 flex w-full max-w-lg flex-col gap-7 text-center">
      <header className="space-y-2">
        <p className="eyebrow">AnyView · Your career, connected</p>
        <h1 className="py-4 text-4xl font-semibold tracking-tight">Good stories.<br />Better conversations.</h1>
        <p className="text-sm text-muted-foreground">
          Get a bird’s-eye view of your career in your Digital Garden. Connect your experience,
          then practice interviews with Harvey and get feedback on every answer.
        </p>
      </header>

      {configured ? (
        <Button
          size="lg"
          className="h-11 self-center px-5 text-base"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError(null);
            signInWithGoogle()
              .catch((err: unknown) => {
                setError(
                  (err as { code?: string }).code === "auth/unauthorized-domain"
                    ? "Sign-in isn't set up for this address yet."
                    : "Couldn't sign in. Please try again.",
                );
              })
              .finally(() => setBusy(false));
          }}
        >
          {busy ? "Opening Google…" : "Sign in with Google"}
        </Button>
      ) : (
        <p role="alert" className="text-sm text-destructive">
          Sign-in isn&apos;t configured for this build (missing NEXT_PUBLIC_FIREBASE_* values).
        </p>
      )}

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      <p className="text-xs text-muted-foreground">
        Access is by invitation: your Google account needs to be on the list. Your sign-in is
        used to keep your Digital Garden and practice sessions yours.{" "}
        <Link href="/privacy" className="underline underline-offset-2 hover:text-foreground">
          Privacy policy
        </Link>
      </p>
    </div>
  );
}
