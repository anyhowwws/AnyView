import type { Brain, EntityKind, Provenance } from "./types";

export interface BrainNode {
  id: string;
  kind: EntityKind;
  label: string;
  title: string;
  detail: string;
  source: Provenance;
}
export interface BrainEdge { from: string; to: string; relation: string }

export const GRAPH_KINDS: EntityKind[] = ["role", "project", "story", "skill", "achievement", "education", "language", "feedback"];
export const KIND_NAMES: Record<EntityKind, string> = {
  role: "Roles", project: "Projects", story: "Stories", skill: "Skills", achievement: "Certifications", education: "Education", language: "Languages", feedback: "Feedback",
};

/** Read-only view of confirmed relationships. No inferred or synthetic edges. */
export function buildBrainGraph(brain: Brain): { nodes: BrainNode[]; edges: BrainEdge[] } {
  const nodes: BrainNode[] = [
    ...brain.roles.map((r) => ({ ...r, kind: "role" as const, title: r.company, detail: [[r.title, r.start_date, r.end_date ?? "Present"].filter(Boolean).join(" · "), ...(r.responsibilities ?? []).map((line) => `• ${line}`)].join("\n") })),
    ...brain.projects.map((p) => ({ ...p, kind: "project" as const, title: p.name, detail: [p.problem, p.action, p.result, p.tech.join(", ")].filter(Boolean).join("\n\n") })),
    ...brain.stories.map((s) => ({ ...s, kind: "story" as const, detail: [s.situation, s.task, s.action, s.result, s.competencies.join(", ")].filter(Boolean).join("\n\n") })),
    ...brain.skills.map((s) => ({ ...s, kind: "skill" as const, title: s.name, detail: `Self-rated depth ${s.depth} of 5` })),
    ...brain.achievements.map((a) => ({ ...a, kind: "achievement" as const, detail: [a.kind, a.issuer, a.achieved_on].filter(Boolean).join(" · ") })),
    ...(brain.education ?? []).map((e) => ({ ...e, kind: "education" as const, title: e.institution, detail: [e.qualification, e.field, e.start_date, e.end_date].filter(Boolean).join(" · ") })),
    ...(brain.languages ?? []).map((l) => ({ ...l, kind: "language" as const, title: l.name, detail: l.proficiency ?? "Proficiency not recorded" })),
    ...(brain.feedback ?? []).map((f) => ({ ...f, kind: "feedback" as const, title: f.given_by, detail: f.content })),
  ];
  const ids = new Set(nodes.map((n) => n.id));
  const edges: BrainEdge[] = [];
  function link(from: string | null, to: string, relation: string) {
    if (from && ids.has(from) && ids.has(to)) edges.push({ from, to, relation });
  }
  brain.projects.forEach((p) => link(p.role_id, p.id, "Project in role"));
  brain.stories.forEach((s) => {
    link(s.role_id, s.id, "Story from role");
    link(s.project_id, s.id, "Story from project");
  });
  brain.skills.forEach((s) => {
    s.project_ids.forEach((p) => link(p, s.id, "Evidence for skill"));
    (s.role_ids ?? []).forEach((r) => link(r, s.id, "Skill used in role"));
  });
  (brain.feedback ?? []).forEach((f) => {
    link(f.role_id, f.id, "Feedback on role");
    link(f.project_id, f.id, "Feedback on project");
  });
  return { nodes, edges };
}
