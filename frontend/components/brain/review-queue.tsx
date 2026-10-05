"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { EntryFields } from "@/components/brain/entry-form";
import { ApiError, confirmProposal, discardProposal } from "@/lib/api";
import { ENTRY_FIELDS, asFormValue, fromFormValue, linkFields, validateEntry, type FieldSpec } from "@/lib/entry-fields";
import type { Brain, Competency, EntityKind, Patch, Proposal } from "@/lib/types";
import type { EventOut } from "@/lib/api";

interface Props {
  proposals: Proposal[];
  competencies: Competency[];
  /** What a draft can be linked to besides this proposal's own drafts. */
  garden?: Pick<Brain, "roles" | "projects">;
  onConfirmed: (out: EventOut, proposalId: string) => void;
  onDiscarded: (brain: Brain, proposalId: string) => void;
}

export function ReviewQueue({ proposals, competencies, garden, onConfirmed, onDiscarded }: Props) {
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
            <ProposalCard proposal={p} competencies={competencies} garden={garden} onConfirmed={onConfirmed} onDiscarded={onDiscarded} />
          </motion.div>
        ))}
      </AnimatePresence>
    </section>
  );
}

type Group = keyof Patch;
// Each Patch group's entity kind, for its field definitions.
const KIND_OF: Record<Group, EntityKind> = {
  roles: "role", projects: "project", stories: "story", skills: "skill",
  achievements: "achievement", education: "education", languages: "language", feedback: "feedback",
};
const problemsOf = (group: Group, draft: object) => {
  const specs = ENTRY_FIELDS[KIND_OF[group]];
  const d = draft as Record<string, unknown>;
  return validateEntry(specs, Object.fromEntries(specs.map((s) => [s.name, asFormValue(d[s.name])])));
};

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
  garden,
  onConfirmed,
  onDiscarded,
}: {
  proposal: Proposal;
  competencies: Competency[];
  garden: Props["garden"];
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
  // After a refused Confirm, every problem shows, not just the touched ones.
  const [attempted, setAttempted] = useState(false);

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
      skills: live(patch.skills).map((d) => ({
        ...d,
        projects: many(d.projects),
        roles: many(d.roles),
        achievements: many(d.achievements),
      })),
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
    const credential = patch.achievements.find((d) => d.key === ref);
    if (credential) return credential.title;
    return ref;
  };
  const unverified = GROUPS.flatMap(({ key }) => patch[key].filter((d) => d.unverified).map((d) => ({ group: key, draft: d })));
  const keptCount = GROUPS.reduce((n, g) => n + patch[g.key].filter((d) => !dropped.has(d.key)).length, 0);
  const invalidCount = GROUPS.reduce(
    (n, g) => n + patch[g.key].filter((d) => !dropped.has(d.key) && Object.keys(problemsOf(g.key, d)).length > 0).length,
    0,
  );

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

  // Where a project, story or feedback draft can sit: a role or project this
  // proposal adds (by key, "r1") or one already in the garden (by label, "R2"),
  // which is how a Patch refers to them. A draft that updates a garden entry
  // stands in for it, so that entry is not offered twice.
  const updated = new Set(GROUPS.flatMap((g) => patch[g.key].map((d) => d.existing).filter(Boolean)));
  const tag = (d: { key: string; existing: string | null }) =>
    dropped.has(d.key) ? " (unticked)" : d.existing ? ` (updates ${d.existing})` : " (new)";
  const linkOptions = {
    roles: [
      ...patch.roles.map((d) => ({ value: d.key, label: `${d.title} · ${d.company}${tag(d)}` })),
      ...(garden?.roles ?? []).filter((r) => !updated.has(r.label)).map((r) => ({ value: r.label, label: `${r.title} · ${r.company}` })),
    ],
    projects: [
      ...patch.projects.map((d) => ({ value: d.key, label: `${d.name}${tag(d)}` })),
      ...(garden?.projects ?? []).filter((p) => !updated.has(p.label)).map((p) => ({ value: p.label, label: p.name })),
    ],
    certs: [],
  };
  // Skills keep their own list of evidenced links (SkillLinks) instead.
  const linksFor = (group: Group): FieldSpec[] => (group === "skills" ? [] : linkFields(KIND_OF[group], linkOptions, "add"));

  function card<G extends Group>(group: G, draft: Patch[G][number]) {
    return (
      <DraftCard
        key={draft.key}
        group={group}
        draft={draft}
        competencies={competencies}
        links={linksFor(group)}
        kept={!dropped.has(draft.key)}
        problems={problemsOf(group, draft)}
        showAll={attempted}
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
            onClick={() => {
              if (invalidCount > 0) return setAttempted(true);
              void act(async () => onConfirmed(await confirmProposal(proposal.id, kept()), proposal.id));
            }}
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
          {attempted && invalidCount > 0 && (
            <span role="status" className="text-sm text-destructive">
              {invalidCount} {invalidCount === 1 ? "entry needs" : "entries need"} fixing first, or untick {invalidCount === 1 ? "it" : "them"}.
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function DraftCard<G extends Group>({
  group,
  draft,
  competencies,
  links,
  kept,
  problems,
  showAll,
  nameOf,
  onKeep,
  onChange,
}: {
  group: G;
  draft: Patch[G][number];
  competencies: Competency[];
  links: FieldSpec[];
  kept: boolean;
  problems: Record<string, string>;
  showAll: boolean;
  nameOf: (ref: string) => string;
  onKeep: (keep: boolean) => void;
  onChange: (fields: Partial<Patch[G][number]>) => void;
}) {
  const d = draft as unknown as Record<string, unknown>;
  const patchOf = (fields: Record<string, unknown>) => fields as unknown as Partial<Patch[G][number]>;
  const specs = [...ENTRY_FIELDS[KIND_OF[group]], ...links];
  // The form's own text, so a half-typed list line or a trailing space is not
  // normalised away mid-keystroke; the draft gets the cleaned value.
  const [texts, setTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(specs.map((s) => [s.name, asFormValue(d[s.name])])),
  );
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const shown = !kept ? {} : showAll ? problems : Object.fromEntries(Object.entries(problems).filter(([n]) => touched.has(n)));

  return (
    <div className={`rounded-lg border p-3 ${kept ? "" : "opacity-50"} ${kept && showAll && Object.keys(problems).length ? "border-destructive/60" : ""}`}>
      <div className="mb-3 flex items-start justify-between gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={kept} onChange={(e) => onKeep(e.target.checked)} className="size-4" />
          <span className="font-medium">
            {draft.existing ? `Updates ${draft.existing}` : "New"}
          </span>
        </label>
        {draft.unverified && <Badge variant="outline">Quote not found</Badge>}
      </div>
      <EntryFields
        specs={specs}
        values={texts}
        errors={shown}
        disabled={!kept}
        onChange={(name, value) => {
          setTexts((t) => ({ ...t, [name]: value }));
          const spec = specs.find((s) => s.name === name)!;
          onChange(patchOf({ [name]: fromFormValue(spec, value) }));
        }}
        onBlur={(name) => setTouched((t) => (t.has(name) ? t : new Set(t).add(name)))}
      />
      {(group === "stories" || group === "skills") && (
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {group === "stories" && (
            <div className="space-y-1.5 sm:col-span-2">
              <span className="text-xs font-semibold text-foreground">Competencies it shows</span>
              <div className="flex flex-wrap gap-1.5" role="group" aria-label="Competencies">
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
                      className={`min-h-8 rounded-full border px-3 py-1 text-xs ${on ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent"}`}
                    >
                      {c.label}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
          {group === "skills" && (
            <>
              {((d.merged_from as string[]) ?? []).length > 0 && (
                // Names folded into this one (ADR 0021). To split one back out,
                // capture it on its own; confirming this card does not add it.
                <p className="text-xs text-muted-foreground sm:col-span-2">
                  Also found as {((d.merged_from as string[]) ?? []).join(", ")}, merged into this one.
                </p>
              )}
              <SkillLinks
                projects={(d.projects as string[]) ?? []}
                roles={(d.roles as string[]) ?? []}
                certifications={(d.achievements as string[]) ?? []}
                quotes={(d.link_evidence as Record<string, string>) ?? {}}
                nameOf={nameOf}
                disabled={!kept}
                onRemove={(ref) =>
                  onChange(
                    patchOf({
                      projects: ((d.projects as string[]) ?? []).filter((r) => r !== ref),
                      roles: ((d.roles as string[]) ?? []).filter((r) => r !== ref),
                      achievements: ((d.achievements as string[]) ?? []).filter((r) => r !== ref),
                    }),
                  )
                }
              />
            </>
          )}
        </div>
      )}
      <blockquote className="mt-3 border-l-2 pl-2 text-xs text-muted-foreground">“{draft.evidence}”</blockquote>
    </div>
  );
}

/** Where a skill was used, and which certifications attest to it, each link
 *  with the quote that justifies it (ADR 0019, 0020). A link to something
 *  already in the garden ("P2") has no quote from this text; it came from the
 *  extraction itself. */
function SkillLinks({
  projects,
  roles,
  certifications,
  quotes,
  nameOf,
  disabled,
  onRemove,
}: {
  projects: string[];
  roles: string[];
  certifications: string[];
  quotes: Record<string, string>;
  nameOf: (ref: string) => string;
  disabled: boolean;
  onRemove: (ref: string) => void;
}) {
  const shared = { quotes, nameOf, disabled, onRemove };
  return (
    <div className="space-y-2 sm:col-span-2">
      <LinkList heading="Used in" refs={[...projects, ...roles]} empty="No role or project in this text shows it." {...shared} />
      {certifications.length > 0 && <LinkList heading="Certified by" refs={certifications} {...shared} />}
    </div>
  );
}

function LinkList({
  heading,
  refs,
  empty,
  quotes,
  nameOf,
  disabled,
  onRemove,
}: {
  heading: string;
  refs: string[];
  empty?: string;
  quotes: Record<string, string>;
  nameOf: (ref: string) => string;
  disabled: boolean;
  onRemove: (ref: string) => void;
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs font-semibold uppercase tracking-[0.11em] text-foreground/75">{heading}</span>
      {refs.length === 0 ? (
        <p className="text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-1">
          {refs.map((ref) => (
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
