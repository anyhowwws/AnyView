"use client";

import { useCallback, useEffect, useState } from "react";
import { CaptureBox } from "@/components/brain/capture-box";
import { CoverageHeatmap } from "@/components/brain/coverage-heatmap";
import { Entities } from "@/components/brain/entities";
import { ReviewQueue } from "@/components/brain/review-queue";
import { AuthShell } from "@/components/shell";
import { BrainGraph } from "@/components/brain/brain-graph";
import { Discover } from "@/components/brain/discover";
import { Network, List, Grid2X2, MessageCircle, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { ApiError, getBrain, listProposals } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Brain, Proposal } from "@/lib/types";

/** Confirmed knowledge, explored as relationships, editable entries, coverage,
 *  or a conversation with Donna about it (ADR 0017). */
export function BrainScreen() {
  const { user } = useAuth();
  const [brain, setBrain] = useState<Brain | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"graph" | "list" | "coverage" | "discover">("graph");
  // An entry to scroll to once the Entries view has rendered (Discover's citations).
  const [focusId, setFocusId] = useState<string | null>(null);

  const reloadGarden = useCallback(() => {
    if (!user) return;
    setError(null);
    Promise.all([getBrain(), listProposals()])
      .then(([b, p]) => {
        setBrain(b);
        setProposals(p);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load your Digital Garden."));
  }, [user]);

  useEffect(() => {
    reloadGarden();
  }, [reloadGarden]);

  useEffect(() => {
    if (view !== "list" || !focusId) return;
    const card = document.getElementById(`entity-${focusId}`);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.focus({ preventScroll: true });
      card.classList.add("is-cited");
      window.setTimeout(() => card.classList.remove("is-cited"), 2400);
    }
    setFocusId(null);
  }, [view, focusId]);

  return (
    <AuthShell pending={proposals.length}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-7">
        <header className="page-heading">
          <div><p className="eyebrow">A bird’s-eye view of your career</p><h1>Your Digital Garden<span className="text-primary">.</span></h1><p>Capture the work you’ve done, cultivate the stories worth remembering, and see the connections grow.</p></div>
          <Link href="/practice" className="workspace-link">Put it into practice <ArrowUpRight size={17} aria-hidden /></Link>
        </header>
        <CaptureBox onProposal={(p) => setProposals((prev) => [...prev, p])} />
        {error && (
          <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <p>{error}</p>
            <Button variant="outline" onClick={reloadGarden}>Retry loading Garden</Button>
          </div>
        )}
        <ReviewQueue
          proposals={proposals}
          competencies={brain?.coverage.competencies ?? []}
          onConfirmed={(out, id) => {
            setBrain(out.brain);
            setProposals((prev) => prev.filter((p) => p.id !== id));
          }}
          onDiscarded={(b, id) => {
            setBrain(b);
            setProposals((prev) => prev.filter((p) => p.id !== id));
          }}
        />
        <div className="brain-section-heading">
          <div><h2 className="text-lg font-semibold">Explore your experience</h2><p className="mt-1 text-sm text-muted-foreground">{brain ? `${brain.roles.length + brain.projects.length + brain.stories.length + brain.skills.length + brain.achievements.length + (brain.education?.length ?? 0) + (brain.languages?.length ?? 0) + (brain.feedback?.length ?? 0)} confirmed entries · ${proposals.length} awaiting review` : "Loading your Digital Garden…"}</p></div>
          <div className="view-switch" role="group" aria-label="Brain view">
            {([{ id: "graph", label: "Graph", Icon: Network }, { id: "list", label: "Entries", Icon: List }, { id: "coverage", label: "Coverage", Icon: Grid2X2 }, { id: "discover", label: "Discover", Icon: MessageCircle }] as const).map(({ id, label, Icon }) => <button key={id} aria-pressed={view === id} onClick={() => setView(id)}><Icon size={16} aria-hidden />{label}</button>)}
          </div>
        </div>
        {!brain && !error && <div className="loading-space" role="status"><Network size={32} aria-hidden /><p>Connecting your experience…</p></div>}
        {brain && view === "graph" && <BrainGraph brain={brain} onBrowse={() => setView("list")} />}
        {brain && view === "coverage" && <div className="workspace-panel"><CoverageHeatmap coverage={brain.coverage} /></div>}
        {brain && view === "list" && <Entities brain={brain} onChanged={(out) => setBrain(out.brain)} />}
        {/* Kept mounted while hidden, so following a citation to Entries and
            coming back does not lose the conversation. */}
        {brain && (
          <div hidden={view !== "discover"}>
            <Discover brain={brain} onOpen={(id) => { setFocusId(id); setView("list"); }} />
          </div>
        )}
      </div>
    </AuthShell>
  );
}
