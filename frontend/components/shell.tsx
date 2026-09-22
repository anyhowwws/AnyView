"use client";

import Link, { useLinkStatus } from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { MotionConfig } from "framer-motion";
import { SignIn } from "@/components/sign-in";
import { Button } from "@/components/ui/button";
import { getBrain } from "@/lib/api";
import { signOut, useAuth } from "@/lib/auth";
import { Brain, AudioLines, Loader2 } from "lucide-react";

/** `useLinkStatus` only works inside a child of the `Link` it reports on, so
 *  the spinner has to be its own component rather than inlined above. Without
 *  this, a tab click gives no feedback until the destination route is fully
 *  fetched and rendered — on a cold or slow load that can take a beat, and in
 *  that gap the tab looks unresponsive even though the click registered. */
function NavPending() {
  const { pending } = useLinkStatus();
  if (!pending) return null;
  return <Loader2 size={13} className="ml-0.5 animate-spin" aria-hidden />;
}

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

  if (user === undefined) return <main className="loading-space" role="status">Opening your workspace…</main>;
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
      aria-current={pathname === href || (href === "/" && pathname === "/brain") ? "page" : undefined}
      className={`workspace-nav-link ${pathname === href || (href === "/" && pathname === "/brain") ? "is-active" : ""}`}
    >
      {href === "/" || href === "/brain" ? <Brain size={16} aria-hidden /> : <AudioLines size={16} aria-hidden />}
      {label}
      {count ? (
        <span className="ml-1.5 rounded-full bg-primary px-1.5 text-xs text-primary-foreground tabular-nums">
          {count}
        </span>
      ) : null}
      <NavPending />
    </Link>
  );

  return (
    <MotionConfig reducedMotion="user">
      <a href="#main-content" className="skip-link">Skip to content</a>
      <header className="workspace-header">
        <Link href="/" className="wordmark" aria-label="AnyView home"><span className="brand-mark"><Brain size={20} aria-hidden /></span>anyview<span className="brand-dot">.</span></Link>
        <nav className="flex items-center gap-1" aria-label="Sections">
          {link("/", "Digital Garden", badge)}
          {link("/practice", "Interview Practice")}
        </nav>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="hidden lg:inline">{user.email}</span>
          <Button variant="ghost" size="sm" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </header>
      <main id="main-content" className="workspace-main">{children}</main>
    </MotionConfig>
  );
}
