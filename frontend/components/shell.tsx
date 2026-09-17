"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { SignIn } from "@/components/sign-in";
import { Button } from "@/components/ui/button";
import { getBrain } from "@/lib/api";
import { signOut, useAuth } from "@/lib/auth";

/** Sign-in gate + top nav around every screen. The Brain badge is the
 *  pending-proposal count; a screen that knows a fresher number passes it. */
export function AuthShell({ children, pending }: { children: React.ReactNode; pending?: number }) {
  const { user, configured } = useAuth();
  const pathname = usePathname();
  const [fetched, setFetched] = useState<number | null>(null);

  useEffect(() => {
    if (!user || pending !== undefined) return;
    getBrain()
      .then((b) => setFetched(b.pending_proposals))
      .catch(() => setFetched(null)); // no database or a transient error: no badge
  }, [user, pending]);

  if (user === undefined) return null;
  if (!user) {
    return (
      <main className="min-h-screen px-4 py-10 sm:px-6 sm:py-16">
        <SignIn configured={configured} />
      </main>
    );
  }

  const badge = pending ?? fetched ?? 0;
  const link = (href: string, label: string, count?: number) => (
    <Link
      href={href}
      className={`rounded-md px-2.5 py-1.5 text-sm ${pathname === href ? "bg-muted font-medium" : "text-muted-foreground hover:text-foreground"}`}
    >
      {label}
      {count ? (
        <span className="ml-1.5 rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums">
          {count}
        </span>
      ) : null}
    </Link>
  );

  return (
    <MotionConfig reducedMotion="user">
      <header className="mx-auto flex w-full max-w-4xl items-center justify-between gap-3 px-4 pt-6 sm:px-6">
        <nav className="flex items-center gap-1" aria-label="Sections">
          {link("/", "Practice")}
          {link("/brain", "Brain", badge)}
        </nav>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="hidden sm:inline">{user.email}</span>
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </header>
      <main className="min-h-screen px-4 py-8 sm:px-6 sm:py-10">{children}</main>
    </MotionConfig>
  );
}
