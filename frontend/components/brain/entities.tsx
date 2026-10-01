"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EntryForm } from "@/components/brain/entry-form";
import { ApiError, addEntity, editEntity, getDump, retireEntity, type EventOut } from "@/lib/api";
import { ENTRY_FIELDS, linkSpecs, monthLabel } from "@/lib/entry-fields";
import type { Achievement, Brain, Education, EntityKind, Feedback, Language, Project, Role, Skill, Story } from "@/lib/types";

// The garden being shown, so any card's editor can offer links to the rest of
// it without every card being handed the whole brain.
const GardenContext = createContext<Brain | null>(null);

interface Props {
  brain: Brain;
  onChanged: (out: EventOut) => void;
}

/** Entities grouped by role: Role → its Projects → their Stories; then Skills
 *  and Achievements. Every card can be edited in place or retired, and links
 *  to the dump it came from. */
export function Entities({ brain, onChanged }: Props) {
  // Which add form is open, and where: `at` is the section (or role) whose
  // button opened it, so the form appears beside that button.
  const [adding, setAdding] = useState<{ kind: EntityKind; at: string; roleId?: string } | null>(null);
  // During a rolling deploy an older API response can lack newly added arrays.
  const education = brain.education ?? [];
  const languages = brain.languages ?? [];
  const feedback = brain.feedback ?? [];
  const labelOf = new Map<string, string>(
    [...brain.roles, ...brain.projects, ...brain.stories, ...brain.skills, ...brain.achievements, ...education, ...languages, ...feedback].map((e) => [e.id, e.label]),
  );
  const projectsOf = (roleId: string | null) => brain.projects.filter((p) => p.role_id === roleId);
  const storiesOf = (roleId: string | null, projectId: string | null) =>
    brain.stories.filter((s) => (projectId ? s.project_id === projectId : s.role_id === roleId && !s.project_id));
  const orphanProjects = brain.projects.filter((p) => !p.role_id || !brain.roles.some((r) => r.id === p.role_id));
  const orphanStories = brain.stories.filter(
    (s) => !s.project_id && (!s.role_id || !brain.roles.some((r) => r.id === s.role_id)),
  );
  const empty = brain.roles.length + brain.projects.length + brain.stories.length + brain.skills.length + brain.achievements.length + education.length + languages.length + feedback.length === 0;

  const added = (out: EventOut) => {
    // Show the user where their new entry landed.
    const before = new Set(labelOf.keys());
    onChanged(out);
    setAdding(null);
    const fresh = allEntities(out.brain).find((e) => !before.has(e.id));
    if (fresh) highlightSoon(fresh.id);
  };
  const addForm = (at: string) =>
    adding && adding.at === at ? (
      <AddEntry kind={adding.kind} brain={brain} roleId={adding.roleId} onAdded={added} onCancel={() => setAdding(null)} />
    ) : null;
  const addButton = (kind: EntityKind, at: string, label = KIND_NAME[kind], roleId?: string) => {
    const open = adding?.kind === kind && adding.at === at;
    return (
      <Button
        key={`${kind}-${at}`}
        type="button"
        variant={open ? "secondary" : "ghost"}
        size="sm"
        className="h-8 gap-1"
        aria-expanded={open}
        onClick={() => setAdding(open ? null : { kind, at, roleId })}
      >
        <Plus className="size-3.5" aria-hidden />
        Add {label.toLowerCase()}
      </Button>
    );
  };
  // One section per kind, always shown so it can be added to while empty.
  const section = (at: string, title: string, kinds: EntityKind[], count: number, children: ReactNode, grid = true) => (
    <div className="space-y-2" aria-labelledby={`entities-${at}`} role="group">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-1">
        <h3 id={`entities-${at}`} className="text-sm font-medium text-muted-foreground">
          {title} <span className="tabular-nums">· {count}</span>
        </h3>
        <div className="flex flex-wrap gap-1 text-primary">{kinds.map((k) => addButton(k, at))}</div>
      </div>
      {addForm(at)}
      {count === 0 && adding?.at !== at && <p className="text-xs text-muted-foreground">None yet.</p>}
      {count > 0 && (grid ? <div className="grid gap-2 sm:grid-cols-2">{children}</div> : <div className="space-y-6">{children}</div>)}
    </div>
  );

  return (
    <GardenContext.Provider value={brain}>
    <section aria-labelledby="entities-heading" className="space-y-6">
      <h2 id="entities-heading" className="text-lg font-semibold tracking-tight">
        What&apos;s growing in your Digital Garden
      </h2>
      {empty && !adding && (
        <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">
          Your Digital Garden is empty. Add an entry in any section below, capture a thought for Donna, or upload a resume.
        </p>
      )}
      {section("roles", "Roles", ["role"], brain.roles.length, brain.roles.map((role) => (
        <div key={role.id} className="space-y-3">
          <EntityCard kind="role" entity={role} title={`${role.title} · ${role.company}`} onChanged={onChanged}
            meta={`${role.start_date ? `${monthLabel(role.start_date)} – ${monthLabel(role.end_date) || "Present"}` : "Dates not set"}${role.level ? ` · ${role.level}` : ""}`}
            details={role.responsibilities ?? []}
          />
          <div className="ml-4 space-y-3 border-l pl-4">
            {projectsOf(role.id).map((p) => (
              <div key={p.id} className="space-y-2">
                <ProjectCard project={p} onChanged={onChanged} />
                <div className="ml-4 space-y-2 border-l pl-4">
                  {storiesOf(role.id, p.id).map((s) => <StoryCard key={s.id} story={s} labelOf={labelOf} onChanged={onChanged} />)}
                </div>
              </div>
            ))}
            {storiesOf(role.id, null).map((s) => <StoryCard key={s.id} story={s} labelOf={labelOf} onChanged={onChanged} />)}
            {addForm(role.id)}
            {adding?.at !== role.id && (
              <div className="flex flex-wrap gap-1 text-muted-foreground">
                {addButton("project", role.id, `Project at ${role.company}`, role.id)}
                {addButton("story", role.id, `Story at ${role.company}`, role.id)}
              </div>
            )}
          </div>
        </div>
      )), false)}
      {section("unlinked", "Projects & stories not linked to a role", ["project", "story"], orphanProjects.length + orphanStories.length, (
        <>
          {orphanProjects.map((p) => <ProjectCard key={p.id} project={p} onChanged={onChanged} />)}
          {orphanStories.map((s) => <StoryCard key={s.id} story={s} labelOf={labelOf} onChanged={onChanged} />)}
        </>
      ), false)}
      {section("skills", "Skills", ["skill"], brain.skills.length, (<>
            {brain.skills.map((k) => (
              <EntityCard key={k.id} kind="skill" entity={k} title={k.name} onChanged={onChanged}
                meta={`depth ${k.depth}/5 · ${DEPTH_NAME[k.depth] ?? ""}${usedIn(k, labelOf)}`}
              />
            ))}
          </>))}
      {section("achievements", "Certifications & achievements", ["achievement"], brain.achievements.length, (<>
            {brain.achievements.map((a) => (
              <EntityCard key={a.id} kind="achievement" entity={a} title={a.title} onChanged={onChanged}
                meta={[a.kind === "credential" ? "Certification" : "Achievement", a.issuer, monthLabel(a.achieved_on)].filter(Boolean).join(" · ")}
              />
            ))}
          </>))}
      {section("education", "Education", ["education"], education.length, (<>
            {education.map((e) => <EntityCard key={e.id} kind="education" entity={e} title={e.institution} onChanged={onChanged}
              meta={[e.qualification, e.field, e.start_date ? `${monthLabel(e.start_date)} – ${monthLabel(e.end_date) || "Ongoing"}` : e.end_date ? `Finished ${monthLabel(e.end_date)}` : null].filter(Boolean).join(" · ")}
            />)}
          </>))}
      {section("languages", "Languages", ["language"], languages.length, (<>
            {languages.map((language) => <EntityCard key={language.id} kind="language" entity={language} title={language.name} onChanged={onChanged}
              meta={language.proficiency ?? "proficiency not recorded"}
            />)}
          </>))}
      {section("feedback", "Feedback", ["feedback"], feedback.length, (<>
            {feedback.map((f) => <FeedbackCard key={f.id} feedback={f} labelOf={labelOf} onChanged={onChanged} />)}
          </>))}
    </section>
    </GardenContext.Provider>
  );
}

function ProjectCard({ project, onChanged }: { project: Project; onChanged: Props["onChanged"] }) {
  return (
    <EntityCard kind="project" entity={project} title={project.name} onChanged={onChanged}
      meta={[project.result, project.tech.length ? project.tech.join(", ") : null].filter(Boolean).join(" · ")}
    />
  );
}

function StoryCard({ story, labelOf, onChanged }: { story: Story; labelOf: Map<string, string>; onChanged: Props["onChanged"] }) {
  return (
    <EntityCard kind="story" entity={story} title={story.title} onChanged={onChanged}
      meta={story.result ?? "no result recorded"}
      badges={story.competencies}
      footnote={story.project_id ? `part of ${labelOf.get(story.project_id) ?? "a project"}` : undefined}
    />
  );
}

function FeedbackCard({ feedback, labelOf, onChanged }: { feedback: Feedback; labelOf: Map<string, string>; onChanged: Props["onChanged"] }) {
  const about = feedback.project_id
    ? labelOf.get(feedback.project_id)
    : feedback.role_id
      ? labelOf.get(feedback.role_id)
      : undefined;
  return (
    <EntityCard kind="feedback" entity={feedback} title={feedback.given_by} onChanged={onChanged}
      meta={[feedback.content, monthLabel(feedback.received_on)].filter(Boolean).join(" · ")}
      footnote={about ? `about ${about}` : undefined}
    />
  );
}

/** " · used in P1, R2 · certified by A3": what evidences a skill (ADR 0019, 0020). */
function usedIn(skill: Skill, labelOf: Map<string, string>): string {
  const labels = (ids: string[]) => ids.map((id) => labelOf.get(id)).filter(Boolean);
  const used = labels([...skill.project_ids, ...(skill.role_ids ?? [])]);
  const certified = labels(skill.achievement_ids ?? []);
  return (used.length ? ` · used in ${used.join(", ")}` : "") + (certified.length ? ` · certified by ${certified.join(", ")}` : "");
}

type Entity = Role | Project | Story | Skill | Achievement | Education | Language | Feedback;

function EntityCard({
  kind, entity, title, meta, badges, details, footnote, onChanged,
}: {
  kind: EntityKind;
  entity: Entity;
  title: string;
  meta?: string;
  badges?: string[];
  details?: string[];
  footnote?: string;
  onChanged: Props["onChanged"];
}) {
  const [editing, setEditing] = useState(false);
  const [confirmingRetire, setConfirmingRetire] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const garden = useContext(GardenContext);

  async function act(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  return (
    // The id lets Discover's citation chips jump straight to this card.
    <article id={`entity-${entity.id}`} tabIndex={-1} className={`entity-card rounded-lg border p-3 ${editing ? "sm:col-span-2" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium">
            <span className="mr-1.5 text-xs text-muted-foreground tabular-nums">{entity.label}</span>
            {title}
          </p>
          {meta && <p className="truncate text-xs text-muted-foreground">{meta}</p>}
          {badges && badges.length > 0 && (
            <p className="mt-1 flex flex-wrap gap-1">
              {badges.map((b) => <Badge key={b} variant="secondary">{b.replace("_", " ")}</Badge>)}
            </p>
          )}
          {details && details.length > 0 && (
            <ul className="mt-1 list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
              {details.map((d) => <li key={d}>{d}</li>)}
            </ul>
          )}
          {footnote && <p className="mt-1 text-xs text-muted-foreground">{footnote}</p>}
        </div>
        {!editing && !confirmingRetire && (
          <div className="flex shrink-0 gap-1">
            <Button variant="ghost" size="sm" className="h-9 sm:h-7" onClick={() => { setError(null); setEditing(true); }} aria-label={`Edit ${title}`}>Edit</Button>
            <Button variant="ghost" size="sm" className="h-9 sm:h-7" disabled={busy} onClick={() => setConfirmingRetire(true)} aria-label={`Retire ${title}`}>
              Retire
            </Button>
          </div>
        )}
        {confirmingRetire && (
          <div className="flex shrink-0 items-center gap-1 text-xs" role="group" aria-label={`Retire ${title}?`}>
            <span className="text-muted-foreground">Retire? It stays in the log.</span>
            <Button variant="destructive" size="sm" disabled={busy}
              onClick={() => void act(async () => { onChanged(await retireEntity(kind, entity.id)); setConfirmingRetire(false); })}
            >
              {busy ? "Retiring…" : "Yes, retire"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmingRetire(false)}>Keep</Button>
          </div>
        )}
      </div>
      {editing && (
        <div className="mt-3 rounded-lg border bg-muted/30 p-3">
          <EntryForm
            specs={[...ENTRY_FIELDS[kind], ...(garden ? linkSpecs(kind, garden, "edit") : [])]}
            initial={entity as unknown as Record<string, unknown>}
            submitLabel="Save changes"
            busyLabel="Saving…"
            busy={busy}
            error={error}
            onlyChanged
            onSubmit={(changed) => void act(async () => { onChanged(await editEntity(kind, entity.id, changed)); setEditing(false); })}
            onCancel={() => { setEditing(false); setError(null); }}
          />
        </div>
      )}
      {error && !editing && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
      <div className="mt-2">
        <button
          type="button"
          className="text-xs text-muted-foreground underline underline-offset-4"
          onClick={() => {
            if (source !== null) return setSource(null);
            void act(async () => setSource((await getDump(entity.source.raw_dump_id)).text));
          }}
        >
          {source === null ? "Show source" : "Hide source"}
        </button>
        {source !== null && (
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs">{source}</pre>
        )}
      </div>
    </article>
  );
}

const KIND_NAME: Record<EntityKind, string> = {
  role: "Role", project: "Project", story: "Story", skill: "Skill", achievement: "Certification",
  education: "Education", language: "Language", feedback: "Feedback",
};
const DEPTH_NAME: Record<number, string> = { 1: "familiar", 2: "used", 3: "regular", 4: "led", 5: "expert" };

function allEntities(b: Brain): Entity[] {
  return [...b.roles, ...b.projects, ...b.stories, ...b.skills, ...b.achievements, ...(b.education ?? []), ...(b.languages ?? []), ...(b.feedback ?? [])];
}

/** Scroll to a card once React has rendered it, and flash its outline. */
function highlightSoon(id: string) {
  window.setTimeout(() => {
    const card = document.getElementById(`entity-${id}`);
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.focus({ preventScroll: true });
    card.classList.add("is-cited");
    window.setTimeout(() => card.classList.remove("is-cited"), 2400);
  }, 50);
}

/** A new entry typed in by hand (ADR 0022): saved at once, no review, with
 *  the form itself kept as its source. Projects, stories and feedback can be
 *  placed under a role (and a story or feedback under a project) here. */
function AddEntry({
  kind, brain, roleId, onAdded, onCancel,
}: {
  kind: EntityKind;
  brain: Brain;
  roleId?: string;
  onAdded: (out: EventOut) => void;
  onCancel: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const specs = [...ENTRY_FIELDS[kind], ...linkSpecs(kind, brain, "add")];
  const role = brain.roles.find((r) => r.id === roleId);
  const initial: Record<string, unknown> = { depth: 3, kind: "credential", role: role?.label ?? "" };

  return (
    <div className="rounded-lg border border-primary/50 bg-card p-4 shadow-sm" role="region" aria-label={`New ${KIND_NAME[kind].toLowerCase()}`}>
      <p className="mb-1 text-sm font-semibold">
        New {KIND_NAME[kind].toLowerCase()}
        {role && <span className="font-normal text-muted-foreground"> at {role.company}</span>}
      </p>
      <p className="mb-4 text-xs text-muted-foreground">
        Saved straight to your garden. Fields marked <span className="text-destructive">*</span> are required.
      </p>
      <EntryForm
        key={`${kind}-${roleId ?? ""}`}
        specs={specs}
        initial={initial}
        submitLabel={`Add ${KIND_NAME[kind].toLowerCase()}`}
        busyLabel="Adding…"
        busy={busy}
        error={error}
        onSubmit={async (fields) => {
          setBusy(true);
          setError(null);
          try {
            onAdded(await addEntity(kind, fields));
          } catch (err) {
            setError(err instanceof ApiError ? err.message : "Something went wrong.");
            setBusy(false);
          }
        }}
        onCancel={onCancel}
      />
    </div>
  );
}
