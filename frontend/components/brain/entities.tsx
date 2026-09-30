"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, editEntity, getDump, retireEntity, type EventOut } from "@/lib/api";
import type { Achievement, Brain, Education, EntityKind, Feedback, Language, Project, Role, Skill, Story } from "@/lib/types";

interface Props {
  brain: Brain;
  onChanged: (out: EventOut) => void;
}

/** Entities grouped by role: Role → its Projects → their Stories; then Skills
 *  and Achievements. Every card can be edited in place or retired, and links
 *  to the dump it came from. */
export function Entities({ brain, onChanged }: Props) {
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

  if (empty) {
    return (
      <section className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        Your Digital Garden is empty. Capture a role, project, story, certification, education entry, language, feedback, or upload a resume or diagram.
      </section>
    );
  }

  return (
    <section aria-labelledby="entities-heading" className="space-y-6">
      <h2 id="entities-heading" className="text-lg font-semibold tracking-tight">
        What&apos;s growing in your Digital Garden
      </h2>
      {brain.roles.map((role) => (
        <div key={role.id} className="space-y-3">
          <EntityCard kind="role" entity={role} title={`${role.title} · ${role.company}`} onChanged={onChanged}
            meta={`${role.start_date?.slice(0, 7) ?? "?"} → ${role.end_date?.slice(0, 7) ?? "now"}${role.level ? ` · ${role.level}` : ""}`}
            fields={[["company", "Company"], ["title", "Title"], ["level", "Level"], ["start_date", "Start (YYYY-MM-DD)"], ["end_date", "End (YYYY-MM-DD)"], ["responsibilities", "Responsibilities, one per line", "lines"]]}
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
          </div>
        </div>
      ))}
      {(orphanProjects.length > 0 || orphanStories.length > 0) && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">Not linked to a role</h3>
          {orphanProjects.map((p) => <ProjectCard key={p.id} project={p} onChanged={onChanged} />)}
          {orphanStories.map((s) => <StoryCard key={s.id} story={s} labelOf={labelOf} onChanged={onChanged} />)}
        </div>
      )}
      {brain.skills.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Skills</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {brain.skills.map((k) => (
              <EntityCard key={k.id} kind="skill" entity={k} title={k.name} onChanged={onChanged}
                meta={`depth ${k.depth}/5${usedIn(k, labelOf)}`}
                fields={[["name", "Skill"], ["depth", "Depth 1–5"]]}
              />
            ))}
          </div>
        </div>
      )}
      {brain.achievements.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Certifications &amp; achievements</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {brain.achievements.map((a) => (
              <EntityCard key={a.id} kind="achievement" entity={a} title={a.title} onChanged={onChanged}
                meta={[a.kind, a.issuer, a.achieved_on].filter(Boolean).join(" · ")}
                fields={[["title", "Title"], ["issuer", "Issuer"], ["achieved_on", "Date (YYYY-MM-DD)"]]}
              />
            ))}
          </div>
        </div>
      )}
      {education.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Education</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {education.map((e) => <EntityCard key={e.id} kind="education" entity={e} title={e.institution} onChanged={onChanged}
              meta={[e.qualification, e.field, e.start_date?.slice(0, 7), e.end_date?.slice(0, 7)].filter(Boolean).join(" · ")}
              fields={[["institution", "Institution"], ["qualification", "Qualification"], ["field", "Field of study"], ["start_date", "Start (YYYY-MM-DD)"], ["end_date", "End (YYYY-MM-DD)"]]}
            />)}
          </div>
        </div>
      )}
      {languages.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Languages</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {languages.map((language) => <EntityCard key={language.id} kind="language" entity={language} title={language.name} onChanged={onChanged}
              meta={language.proficiency ?? "proficiency not recorded"}
              fields={[["name", "Language"], ["proficiency", "Proficiency"]]}
            />)}
          </div>
        </div>
      )}
      {feedback.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-muted-foreground">Feedback</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {feedback.map((f) => <FeedbackCard key={f.id} feedback={f} labelOf={labelOf} onChanged={onChanged} />)}
          </div>
        </div>
      )}
    </section>
  );
}

function ProjectCard({ project, onChanged }: { project: Project; onChanged: Props["onChanged"] }) {
  return (
    <EntityCard kind="project" entity={project} title={project.name} onChanged={onChanged}
      meta={[project.result, project.tech.length ? project.tech.join(", ") : null].filter(Boolean).join(" · ")}
      fields={[["name", "Name"], ["problem", "Problem", true], ["action", "What you did", true], ["result", "Result", true]]}
    />
  );
}

function StoryCard({ story, labelOf, onChanged }: { story: Story; labelOf: Map<string, string>; onChanged: Props["onChanged"] }) {
  return (
    <EntityCard kind="story" entity={story} title={story.title} onChanged={onChanged}
      meta={story.result ?? "no result recorded"}
      badges={story.competencies}
      fields={[["title", "Title"], ["situation", "Situation", true], ["task", "Task", true], ["action", "Action", true], ["result", "Result", true]]}
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
      meta={[feedback.content, feedback.received_on].filter(Boolean).join(" · ")}
      fields={[["given_by", "Who said it"], ["content", "What they said", true], ["received_on", "Date (YYYY-MM-DD)"]]}
      footnote={about ? `about ${about}` : undefined}
    />
  );
}

/** " · used in P1, R2": the projects and roles that evidence a skill (ADR 0019). */
function usedIn(skill: Skill, labelOf: Map<string, string>): string {
  const labels = [...skill.project_ids, ...(skill.role_ids ?? [])].map((id) => labelOf.get(id)).filter(Boolean);
  return labels.length ? ` · used in ${labels.join(", ")}` : "";
}

type Entity = Role | Project | Story | Skill | Achievement | Education | Language | Feedback;
// "lines" edits a list of strings as one textarea, a line per item.
type FieldSpec = [name: string, label: string, multiline?: boolean | "lines"];

function asText(value: unknown): string {
  if (Array.isArray(value)) return value.join("\n");
  return value == null ? "" : String(value);
}

function EntityCard({
  kind, entity, title, meta, badges, details, fields, footnote, onChanged,
}: {
  kind: EntityKind;
  entity: Entity;
  title: string;
  meta?: string;
  badges?: string[];
  details?: string[];
  fields: FieldSpec[];
  footnote?: string;
  onChanged: Props["onChanged"];
}) {
  const [editing, setEditing] = useState(false);
  const [confirmingRetire, setConfirmingRetire] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const raw = entity as unknown as Record<string, unknown>;

  function startEdit() {
    setValues(Object.fromEntries(fields.map(([n]) => [n, asText(raw[n])])));
    setEditing(true);
  }

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

  async function save() {
    const changed: Record<string, unknown> = {};
    for (const [n, , multi] of fields) {
      if (values[n] === asText(raw[n])) continue;
      if (multi === "lines") changed[n] = values[n].split("\n").map((l) => l.trim()).filter(Boolean);
      else changed[n] = n === "depth" ? Number(values[n]) : values[n] || null;
    }
    if (Object.keys(changed).length === 0) return setEditing(false);
    await act(async () => {
      onChanged(await editEntity(kind, entity.id, changed));
      setEditing(false);
    });
  }

  return (
    // The id lets Discover's citation chips jump straight to this card.
    <article id={`entity-${entity.id}`} tabIndex={-1} className="entity-card rounded-lg border p-3">
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
            <Button variant="ghost" size="sm" className="h-9 sm:h-7" onClick={startEdit} aria-label={`Edit ${title}`}>Edit</Button>
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
        <form className="mt-3 grid gap-2 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); void save(); }}>
          {fields.map(([n, label, multi]) => {
            const props = {
              value: values[n] ?? "",
              placeholder: label,
              "aria-label": label,
              onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setValues((v) => ({ ...v, [n]: e.target.value })),
            };
            return <div key={n} className={multi ? "sm:col-span-2" : ""}>{multi ? <Textarea rows={multi === "lines" ? 4 : 2} {...props} /> : <Input {...props} />}</div>;
          })}
          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" size="sm" disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>Cancel</Button>
          </div>
        </form>
      )}
      {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
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
