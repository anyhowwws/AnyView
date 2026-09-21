"use client";

import { useEffect, useState } from "react";
import { CaptureBox } from "@/components/brain/capture-box";
import { CoverageHeatmap } from "@/components/brain/coverage-heatmap";
import { Entities } from "@/components/brain/entities";
import { ReviewQueue } from "@/components/brain/review-queue";
import { AuthShell } from "@/components/shell";
import { BrainGraph } from "@/components/brain/brain-graph";
import { Network, List, Grid2X2, ArrowUpRight } from "lucide-react";
import Link from "next/link";
import { ApiError, getBrain, listProposals } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Brain, Proposal } from "@/lib/types";

/** Confirmed knowledge, explored as relationships, editable entries, or coverage. */
export function BrainScreen() {
  const { user } = useAuth();
  const [brain, setBrain] = useState<Brain | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"graph" | "list" | "coverage">("graph");

  useEffect(() => {
    if (!user) return;
    Promise.all([getBrain(), listProposals()])
      .then(([b, p]) => {
        setBrain(b);
        setProposals(p);
      })
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Couldn't load your brain."));
  }, [user]);

  return (
    <AuthShell pending={proposals.length}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-7">
        <header className="page-heading">
          <div><p className="eyebrow">Your personal knowledge space</p><h1>Your second brain<span className="text-primary">.</span></h1><p>The work you’ve done. The stories worth remembering. All connected.</p></div>
          <Link href="/" className="workspace-link">Put it into practice <ArrowUpRight size={17} aria-hidden /></Link>
        </header>
        <CaptureBox onProposal={(p) => setProposals((prev) => [...prev, p])} />
        {error && (
          <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="brain-section-heading">
          <div><h2 className="text-lg font-semibold">Explore your experience</h2><p className="mt-1 text-sm text-muted-foreground">{brain ? `${brain.roles.length + brain.projects.length + brain.stories.length + brain.skills.length + brain.achievements.length} confirmed entries · ${proposals.length} awaiting review` : "Loading your knowledge space…"}</p></div>
          <div className="view-switch" role="group" aria-label="Brain view">
            {([{ id: "graph", label: "Graph", Icon: Network }, { id: "list", label: "Entries", Icon: List }, { id: "coverage", label: "Coverage", Icon: Grid2X2 }] as const).map(({ id, label, Icon }) => <button key={id} aria-pressed={view === id} onClick={() => setView(id)}><Icon size={16} aria-hidden />{label}</button>)}
          </div>
        </div>
        {!brain && !error && <div className="loading-space" role="status"><Network size={32} aria-hidden /><p>Connecting your experience…</p></div>}
        {brain && view === "graph" && <BrainGraph brain={brain} onBrowse={() => setView("list")} />}
        {brain && view === "coverage" && <div className="workspace-panel"><CoverageHeatmap coverage={brain.coverage} /></div>}
        {brain && view === "list" && <Entities brain={brain} onChanged={(out) => setBrain(out.brain)} />}
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
      </div>
    </AuthShell>
  );
}
