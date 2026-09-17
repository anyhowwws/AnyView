"use client";

import { useEffect, useState } from "react";
import { CaptureBox } from "@/components/brain/capture-box";
import { CoverageHeatmap } from "@/components/brain/coverage-heatmap";
import { Entities } from "@/components/brain/entities";
import { ReviewQueue } from "@/components/brain/review-queue";
import { AuthShell } from "@/components/shell";
import { ApiError, getBrain, listProposals } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Brain, Proposal } from "@/lib/types";

/** The Brain screen (brief: capture box pinned at the top, coverage heatmap
 *  as the hero, review queue with a badge, entities grouped by role). */
export function BrainScreen() {
  const { user } = useAuth();
  const [brain, setBrain] = useState<Brain | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [error, setError] = useState<string | null>(null);

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
      <div className="mx-auto flex w-full max-w-4xl flex-col gap-8">
        <CaptureBox onProposal={(p) => setProposals((prev) => [...prev, p])} />
        {error && (
          <p role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}
        {brain && <CoverageHeatmap coverage={brain.coverage} />}
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
        {brain && <Entities brain={brain} onChanged={(out) => setBrain(out.brain)} />}
      </div>
    </AuthShell>
  );
}
