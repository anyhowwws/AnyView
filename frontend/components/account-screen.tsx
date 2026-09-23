"use client";

import { useState } from "react";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { AuthShell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, eraseAccount } from "@/lib/api";
import { deleteSignIn } from "@/lib/auth";
import { clear as clearInterview } from "@/lib/store";

const PHRASE = "delete my data";

type Done = { files: number; rows: number; signInRemoved: boolean };

/** Account page. Its one job today: erase everything (ADR 0018).
 *  The finished state renders outside the sign-in gate, because erasing
 *  signs the user out and the gate would otherwise replace this message. */
export function AccountPage() {
  const [done, setDone] = useState<Done | null>(null);
  if (done) return <Erased done={done} />;
  return (
    <AuthShell>
      <EraseAccount onErased={setDone} />
    </AuthShell>
  );
}

function EraseAccount({ onErased }: { onErased: (d: Done) => void }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const armed = typed.trim().toLowerCase() === PHRASE;

  async function erase() {
    setBusy(true);
    setError(null);
    try {
      const out = await eraseAccount();
      clearInterview();
      const signInRemoved = await deleteSignIn();
      onErased({ ...out, signInRemoved });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Nothing was erased.");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-7">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Your account</p>
          <h1>Your data<span className="text-primary">.</span></h1>
          <p>Everything you give AnyView is yours. You can erase all of it at any time.</p>
        </div>
      </header>

      <section className="workspace-panel erase-panel" aria-labelledby="erase-heading">
        <h2 id="erase-heading" className="flex items-center gap-2 text-lg font-semibold">
          <ShieldAlert size={20} aria-hidden className="text-destructive" />
          Delete my data
        </h2>
        <p className="text-sm text-muted-foreground">This erases your account permanently. There is no undo.</p>

        <div className="grid gap-5 sm:grid-cols-2">
          <div>
            <h3 className="text-sm font-semibold">Deleted now</h3>
            <ul className="erase-list">
              <li>Every entry in your Digital Garden, and its full history</li>
              <li>Everything you captured or uploaded, including your resume and its text</li>
              <li>Suggestions waiting in your review queue</li>
              <li>Recorded interview answers</li>
              <li>Usage records tied to your account</li>
              <li>Your Google sign-in with AnyView</li>
            </ul>
          </div>
          <div>
            <h3 className="text-sm font-semibold">Worth knowing</h3>
            <ul className="erase-list">
              <li>Database backups are kept for 7 days, so your data is gone from those within about a week.</li>
              <li>Interview reports you downloaded stay on your own device.</li>
              <li>You can sign in again afterwards and start with an empty garden.</li>
            </ul>
          </div>
        </div>

        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (armed && !busy) void erase();
          }}
        >
          <label htmlFor="erase-confirm" className="text-sm">
            Type <strong>{PHRASE}</strong> to confirm.
          </label>
          <Input
            id="erase-confirm"
            value={typed}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            onChange={(e) => setTyped(e.target.value)}
          />
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
          <div>
            <Button type="submit" variant="destructive" disabled={!armed || busy}>
              {busy ? "Erasing…" : "Delete my data"}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}

function Erased({ done }: { done: Done }) {
  return (
    <main className="min-h-screen px-4 py-10 sm:px-6 sm:py-16">
      <section className="workspace-panel mx-auto flex max-w-xl flex-col gap-4" role="status">
        <p className="eyebrow">Done</p>
        <h1 className="text-2xl font-semibold">Your data has been deleted.</h1>
        <p className="text-sm text-muted-foreground">
          {plural(done.rows, "record")} and {plural(done.files, "file")} were erased. Backups age out within
          about a week.
        </p>
        {!done.signInRemoved && (
          <p className="text-sm text-muted-foreground">
            You&apos;re signed out. Your Google sign-in record (just your email) couldn&apos;t be removed because the
            sign-in was too old; it holds none of your data, and it goes if you sign in and erase again.
          </p>
        )}
        <div>
          <Link href="/" className="workspace-link">Back to AnyView</Link>
        </div>
      </section>
    </main>
  );
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}
