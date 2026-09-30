"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
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
        Donna proposed these from what you gave her. Edit anything, untick what you don&apos;t
        want, then confirm. Every entry keeps its exact evidence quote, and every skill link
        shows the words that justify it.
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
  { key: "achievements", label: "Certifications & achievements" },
  { key: "education", label: "Education" },
  { key: "languages", label: "Languages" },
  { key: "feedback", label: "Feedback" },
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
  const [patch, setPatch] = useState<Patch>(() => ({
    ...structuredClone(proposal.patch),
    education: proposal.patch.education ?? [],
    languages: proposal.patch.languages ?? [],
    feedback: proposal.patch.feedback ?? [],
  }));
  // Drafts whose quote could not be found start unticked (ADR 0019): the user
  // sees them, but nothing unverified is confirmed by default.
  const [dropped, setDropped] = useState<Set<string>>(
    () => new Set(GROUPS.flatMap((g) => (proposal.patch[g.key] ?? []).filter((d) => d.unverified).map((d) => d.key))),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // What gets confirmed: the ticked drafts, with any link to an unticked one
  // cut. Sending "p1" after p1 was unticked would be a reference to nothing,
  // and the server would refuse the whole patch.
  const kept = (): Patch => {
    const live = <T extends { key: string }>(drafts: T[]) => drafts.filter((d) => !dropped.has(d.key));
    const one = (ref: string | null) => (ref && dropped.has(ref) ? null : ref);
    const many = (refs: string[] = []) => refs.filter((r) => !dropped.has(r));
    return {
      roles: live(patch.roles),
      projects: live(patch.projects).map((d) => ({ ...d, role: one(d.role) })),
      stories: live(patch.stories).map((d) => ({ ...d, role: one(d.role), project: one(d.project) })),
      skills: live(patch.skills).map((d) => ({ ...d, projects: many(d.projects), roles: many(d.roles) })),
      achievements: live(patch.achievements),
      education: live(patch.education),
      languages: live(patch.languages),
      feedback: live(patch.feedback).map((d) => ({ ...d, role: one(d.role), project: one(d.project) })),
    };
  };
  // A readable name for a link target: a draft in this patch, or a label for
  // something already in the garden.
  const nameOf = (ref: string): string => {
    const role = patch.roles.find((d) => d.key === ref);
    if (role) return `${role.title} · ${role.company}`;
    const project = patch.projects.find((d) => d.key === ref);
    if (project) return project.name;
    return ref;
  };
  const unverified = GROUPS.flatMap(({ key }) => patch[key].filter((d) => d.unverified).map((d) => ({ group: key, draft: d })));
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

  function card<G extends Group>(group: G, draft: Patch[G][number]) {
    return (
      <DraftCard
        key={draft.key}
        group={group}
        draft={draft}
        competencies={competencies}
        kept={!dropped.has(draft.key)}
        nameOf={nameOf}
        onKeep={(keep) =>
          setDropped((prev) => {
            const next = new Set(prev);
            if (keep) next.delete(draft.key);
            else next.add(draft.key);
            return next;
          })
        }
        onChange={(fields) => update(group, draft.key, fields)}
      />
    );
  }

  const source =
    proposal.dump_kind === "text" ? "from a capture" : proposal.dump_kind === "resume_pdf" ? "from a PDF resume" : "from a Word resume";

  return (
    <Card>
      <CardHeader>
        <CardDescription>
          New proposal {source} · {new Date(proposal.created_at).toLocaleString()}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {GROUPS.map(({ key, label }) => {
          const verified = patch[key].filter((d) => !d.unverified);
          return verified.length ? (
            <div key={key} className="space-y-2">
              <h3 className="review-section-label">{label}</h3>
              {verified.map((draft) => card(key, draft))}
            </div>
          ) : null;
        })}
        {unverified.length > 0 && (
          <div className="space-y-2">
            <h3 className="review-section-label">Couldn&apos;t verify</h3>
            <p className="text-xs text-muted-foreground">
              Donna&apos;s quote for these wasn&apos;t found in your text, so they start unticked. Tick
              any that are right.
            </p>
            {unverified.map(({ group, draft }) => card(group, draft))}
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button
            className="h-11 px-5 text-base"
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
  nameOf,
  onKeep,
  onChange,
}: {
  group: G;
  draft: Patch[G][number];
  competencies: Competency[];
  kept: boolean;
  nameOf: (ref: string) => string;
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
        <span className="text-xs font-semibold uppercase tracking-[0.11em] text-foreground/75">{label}</span>
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
        {draft.unverified && <Badge variant="outline">Quote not found</Badge>}
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
            <label className="flex flex-col gap-0.5 sm:col-span-2">
              <span className="text-xs font-semibold uppercase tracking-[0.11em] text-foreground/75">
                Responsibilities, one per line
              </span>
              <Textarea
                rows={3}
                placeholder="—"
                disabled={!kept}
                value={((d.responsibilities as string[]) ?? []).join("\n")}
                onChange={(e) => onChange(patchOf({ responsibilities: e.target.value.split("\n") }))}
                onBlur={(e) =>
                  onChange(patchOf({ responsibilities: e.target.value.split("\n").map((l) => l.trim()).filter(Boolean) }))
                }
              />
            </label>
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
            <SkillLinks
              projects={(d.projects as string[]) ?? []}
              roles={(d.roles as string[]) ?? []}
              quotes={(d.link_evidence as Record<string, string>) ?? {}}
              nameOf={nameOf}
              disabled={!kept}
              onRemove={(ref) =>
                onChange(
                  patchOf({
                    projects: ((d.projects as string[]) ?? []).filter((r) => r !== ref),
                    roles: ((d.roles as string[]) ?? []).filter((r) => r !== ref),
                  }),
                )
              }
            />
          </>
        )}
        {group === "achievements" && (
          <>
            {text("title", "Title")}
            {text("issuer", "Issuer")}
            {text("achieved_on", "Date (YYYY-MM-DD)")}
          </>
        )}
        {group === "education" && (
          <>
            {text("institution", "Institution")}
            {text("qualification", "Qualification")}
            {text("field", "Field of study")}
            <div className="grid grid-cols-2 gap-2">{text("start_date", "Start (YYYY-MM-DD)")}{text("end_date", "End (YYYY-MM-DD)")}</div>
          </>
        )}
        {group === "languages" && <>{text("name", "Language")}{text("proficiency", "Proficiency")}</>}
        {group === "feedback" && (
          <>
            {text("given_by", "Who said it")}
            <div className="sm:col-span-2">{text("content", "What they said", true)}</div>
            {text("received_on", "Date (YYYY-MM-DD)")}
          </>
        )}
      </div>
      <blockquote className="mt-2 border-l-2 pl-2 text-xs text-muted-foreground">“{draft.evidence}”</blockquote>
    </div>
  );
}

/** Where a skill was used, each link with the quote that justifies it
 *  (ADR 0019). A link to something already in the garden ("P2") has no quote
 *  from this text; it came from the extraction itself. */
function SkillLinks({
  projects,
  roles,
  quotes,
  nameOf,
  disabled,
  onRemove,
}: {
  projects: string[];
  roles: string[];
  quotes: Record<string, string>;
  nameOf: (ref: string) => string;
  disabled: boolean;
  onRemove: (ref: string) => void;
}) {
  const links = [...projects, ...roles];
  return (
    <div className="space-y-1 sm:col-span-2">
      <span className="text-xs font-semibold uppercase tracking-[0.11em] text-foreground/75">Used in</span>
      {links.length === 0 ? (
        <p className="text-xs text-muted-foreground">No role or project in this text shows it.</p>
      ) : (
        <ul className="space-y-1">
          {links.map((ref) => (
            <li key={ref} className="flex items-start justify-between gap-2 rounded-md bg-muted/50 px-2 py-1 text-xs">
              <span className="min-w-0">
                <span className="font-medium">{nameOf(ref)}</span>
                {quotes[ref] && <span className="block text-muted-foreground">“{quotes[ref]}”</span>}
              </span>
              <button
                type="button"
                disabled={disabled}
                onClick={() => onRemove(ref)}
                aria-label={`Remove the link to ${nameOf(ref)}`}
                className="shrink-0 rounded px-1.5 text-muted-foreground hover:text-foreground disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
