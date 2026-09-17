"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, confirmProposal, discardProposal } from "@/lib/api";
import type { Brain, Competency, Patch, Proposal } from "@/lib/types";
import type { EventOut } from "@/lib/api";

interface Props {
  proposals: Proposal[];
  competencies: Competency[];
  onConfirmed: (out: EventOut, proposalId: string) => void;
  onDiscarded: (brain: Brain, proposalId: string) => void;
}

export function ReviewQueue({ proposals, competencies, onConfirmed, onDiscarded }: Props) {
  if (proposals.length === 0) return null;
  return (
    <section aria-labelledby="queue-heading" className="space-y-3">
      <h2 id="queue-heading" className="text-lg font-semibold tracking-tight">
        Review queue <Badge variant="secondary">{proposals.length}</Badge>
      </h2>
      <p className="text-sm text-muted-foreground">
        Maya proposed these from what you gave her. Edit anything, untick what you don&apos;t
        want, then confirm. Each card shows the exact words it came from.
      </p>
      <AnimatePresence initial={false}>
        {proposals.map((p) => (
          <motion.div key={p.id} layout exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.25 }}>
            <ProposalCard proposal={p} competencies={competencies} onConfirmed={onConfirmed} onDiscarded={onDiscarded} />
          </motion.div>
        ))}
      </AnimatePresence>
    </section>
  );
}

type Group = keyof Patch;
const GROUPS: { key: Group; label: string }[] = [
  { key: "roles", label: "Roles" },
  { key: "projects", label: "Projects" },
  { key: "stories", label: "Stories" },
  { key: "skills", label: "Skills" },
  { key: "achievements", label: "Achievements" },
];

function ProposalCard({
  proposal,
  competencies,
  onConfirmed,
  onDiscarded,
}: {
  proposal: Proposal;
  competencies: Competency[];
  onConfirmed: Props["onConfirmed"];
  onDiscarded: Props["onDiscarded"];
}) {
  const [patch, setPatch] = useState<Patch>(structuredClone(proposal.patch));
  const [dropped, setDropped] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const kept = (): Patch => ({
    roles: patch.roles.filter((d) => !dropped.has(d.key)),
    projects: patch.projects.filter((d) => !dropped.has(d.key)),
    stories: patch.stories.filter((d) => !dropped.has(d.key)),
    skills: patch.skills.filter((d) => !dropped.has(d.key)),
    achievements: patch.achievements.filter((d) => !dropped.has(d.key)),
  });
  const keptCount = GROUPS.reduce((n, g) => n + patch[g.key].filter((d) => !dropped.has(d.key)).length, 0);

  function update<G extends Group>(group: G, key: string, fields: Partial<Patch[G][number]>) {
    setPatch((prev) => ({
      ...prev,
      [group]: prev[group].map((d) => (d.key === key ? { ...d, ...fields } : d)),
    }));
  }

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
      setBusy(false);
    }
  }

  const source =
    proposal.dump_kind === "text" ? "from a dump" : proposal.dump_kind === "resume_pdf" ? "from a PDF resume" : "from a Word resume";

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          Proposal {source} · {new Date(proposal.created_at).toLocaleString()}
        </CardDescription>
        {proposal.dump_excerpt && (
          <CardTitle className="text-sm font-normal text-muted-foreground line-clamp-2">
            “{proposal.dump_excerpt}”
          </CardTitle>
        )}
      </CardHeader>
      <CardContent className="space-y-5">
        {GROUPS.map(({ key, label }) =>
          patch[key].length ? (
            <div key={key} className="space-y-2">
              <h3 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</h3>
              {patch[key].map((draft) => (
                <DraftCard
                  key={draft.key}
                  group={key}
                  draft={draft}
                  competencies={competencies}
                  kept={!dropped.has(draft.key)}
                  onKeep={(keep) =>
                    setDropped((prev) => {
                      const next = new Set(prev);
                      if (keep) next.delete(draft.key);
                      else next.add(draft.key);
                      return next;
                    })
                  }
                  onChange={(fields) => update(key, draft.key, fields)}
                />
              ))}
            </div>
          ) : null,
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            className="h-10"
            disabled={busy || keptCount === 0}
            onClick={() => void act(async () => onConfirmed(await confirmProposal(proposal.id, kept()), proposal.id))}
          >
            {busy ? "Saving…" : `Confirm ${keptCount} ${keptCount === 1 ? "entry" : "entries"}`}
          </Button>
          <Button
            variant="ghost"
            className="h-10"
            disabled={busy}
            onClick={() => void act(async () => onDiscarded(await discardProposal(proposal.id), proposal.id))}
          >
            Discard all
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function DraftCard<G extends Group>({
  group,
  draft,
  competencies,
  kept,
  onKeep,
  onChange,
}: {
  group: G;
  draft: Patch[G][number];
  competencies: Competency[];
  kept: boolean;
  onKeep: (keep: boolean) => void;
  onChange: (fields: Partial<Patch[G][number]>) => void;
}) {
  const d = draft as unknown as Record<string, unknown>;
  const patchOf = (fields: Record<string, unknown>) => fields as unknown as Partial<Patch[G][number]>;
  const text = (name: string, label: string, multiline = false) => {
    const value = (d[name] as string | null) ?? "";
    const props = {
      value,
      placeholder: "—",
      onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
        onChange(patchOf({ [name]: e.target.value || null })),
      disabled: !kept,
    };
    // A visible caption, so the field keeps its name once it has a value.
    return (
      <label className="flex flex-col gap-0.5">
        <span className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</span>
        {multiline ? <Textarea rows={2} {...props} /> : <Input {...props} />}
      </label>
    );
  };

  return (
    <div className={`rounded-lg border p-3 ${kept ? "" : "opacity-50"}`}>
      <div className="mb-2 flex items-start justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={kept} onChange={(e) => onKeep(e.target.checked)} className="size-4" />
          <span className="font-medium">
            {draft.existing ? `Updates ${draft.existing}` : "New"}
          </span>
        </label>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {group === "roles" && (
          <>
            {text("company", "Company")}
            {text("title", "Title")}
            {text("level", "Level (e.g. senior)")}
            <div className="grid grid-cols-2 gap-2">
              {text("start_date", "Start (YYYY-MM-DD)")}
              {text("end_date", "End (blank = now)")}
            </div>
          </>
        )}
        {group === "projects" && (
          <>
            <div className="sm:col-span-2">{text("name", "Project name")}</div>
            {text("problem", "Problem", true)}
            {text("action", "What you did", true)}
            <div className="sm:col-span-2">{text("result", "Result", true)}</div>
          </>
        )}
        {group === "stories" && (
          <>
            <div className="sm:col-span-2">{text("title", "Story title")}</div>
            {text("situation", "Situation", true)}
            {text("task", "Task", true)}
            {text("action", "Action", true)}
            {text("result", "Result", true)}
            <div className="flex flex-wrap gap-1.5 sm:col-span-2" role="group" aria-label="Competencies">
              {competencies.map((c) => {
                const on = ((d.competencies as string[]) ?? []).includes(c.key);
                return (
                  <button
                    key={c.key}
                    type="button"
                    disabled={!kept}
                    aria-pressed={on}
                    onClick={() => {
                      const cur = (d.competencies as string[]) ?? [];
                      onChange(patchOf({ competencies: on ? cur.filter((k) => k !== c.key) : [...cur, c.key] }));
                    }}
                    className={`rounded-full border px-2.5 py-0.5 text-xs ${on ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground"}`}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>
          </>
        )}
        {group === "skills" && (
          <>
            {text("name", "Skill")}
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Depth</span>
              <input
                type="range"
                min={1}
                max={5}
                value={(d.depth as number) ?? 3}
                disabled={!kept}
                aria-label="Depth, 1 to 5"
                onChange={(e) => onChange(patchOf({ depth: Number(e.target.value) }))}
              />
              <span className="tabular-nums">{(d.depth as number) ?? 3}/5</span>
            </label>
          </>
        )}
        {group === "achievements" && (
          <>
            {text("title", "Title")}
            {text("issuer", "Issuer")}
            {text("achieved_on", "Date (YYYY-MM-DD)")}
          </>
        )}
      </div>
      <blockquote className="mt-2 border-l-2 pl-2 text-xs text-muted-foreground">“{draft.evidence}”</blockquote>
    </div>
  );
}
