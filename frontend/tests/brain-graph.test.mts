import assert from "node:assert/strict";
import { test } from "node:test";
import { buildBrainGraph } from "../lib/brain-graph.ts";
import { visibleConstellationLabels, type ConstellationPoint } from "../lib/constellation.ts";
import type { Brain } from "../lib/types.ts";

const source = { raw_dump_id: "dump", event_id: 1 };
function fixture(): Brain {
  return {
    roles: [{ id: "r", label: "R1", company: "Test employer", title: "Architect", start_date: null, end_date: null, level: null, responsibilities: [], source }],
    projects: [{ id: "p", label: "P1", role_id: "r", name: "Migration", problem: null, action: null, result: "Reduced costs", tech: [], metrics: [], source }],
    stories: [{ id: "s", label: "S1", role_id: "r", project_id: "p", title: "Cutover", situation: null, task: null, action: null, result: null, competencies: [], source }],
    skills: [{ id: "k", label: "K1", name: "Terraform", depth: 4, project_ids: ["p"], role_ids: [], source }],
    achievements: [{ id: "a", label: "A1", title: "Certification", kind: "credential", issuer: null, achieved_on: null, source }],
    education: [], languages: [], feedback: [],
    coverage: { competencies: [], roles: [], cells: {} }, pending_proposals: 2,
  };
}

test("maps confirmed relationships and preserves isolated achievements", () => {
  const graph = buildBrainGraph(fixture());
  assert.equal(graph.nodes.length, 5);
  assert.deepEqual(graph.edges.map((e) => [e.from, e.to]), [["r", "p"], ["r", "s"], ["p", "s"], ["p", "k"]]);
  assert.equal(graph.nodes.find((n) => n.id === "a")?.title, "Certification");
  assert.ok(graph.edges.every((e) => e.from !== "a" && e.to !== "a"));
});

test("a skill used in a role's ongoing work links to the role (ADR 0019)", () => {
  const brain = fixture();
  brain.roles[0].responsibilities = ["EKS day-2 operations"];
  brain.skills[0].role_ids = ["r"];
  const graph = buildBrainGraph(brain);
  assert.ok(graph.edges.some((e) => e.from === "r" && e.to === "k" && e.relation === "Skill used in role"));
  assert.match(graph.nodes.find((n) => n.id === "r")?.detail ?? "", /• EKS day-2 operations/);
});

test("does not draw links to retired or missing entities", () => {
  const brain = fixture();
  brain.roles = [];
  brain.projects = [];
  assert.deepEqual(buildBrainGraph(brain).edges, []);
});

test("empty brain has no synthetic nodes or edges", () => {
  const brain = fixture();
  brain.roles = []; brain.projects = []; brain.stories = []; brain.skills = []; brain.achievements = []; brain.education = []; brain.languages = [];
  assert.deepEqual(buildBrainGraph(brain), { nodes: [], edges: [] });
});

test("feedback complements the graph: it becomes a node and links to what it is about", () => {
  const brain = fixture();
  brain.feedback = [
    { id: "f", label: "F1", role_id: "r", project_id: null, given_by: "Manager", content: "Owned it end to end.", received_on: null, source },
  ];
  const graph = buildBrainGraph(brain);
  assert.equal(graph.nodes.length, 6);
  const feedbackNode = graph.nodes.find((n) => n.id === "f");
  assert.equal(feedbackNode?.kind, "feedback");
  assert.equal(feedbackNode?.title, "Manager");
  assert.ok(graph.edges.some((e) => e.from === "r" && e.to === "f"));
});

test("a feedback entry with no role or project link stands on its own", () => {
  const brain = fixture();
  brain.feedback = [
    { id: "f", label: "F1", role_id: null, project_id: null, given_by: "Client", content: "Great to work with.", received_on: null, source },
  ];
  const graph = buildBrainGraph(brain);
  assert.ok(graph.edges.every((e) => e.from !== "f" && e.to !== "f"));
});

test("suppresses overlapping constellation labels deterministically", () => {
  const nodes = buildBrainGraph(fixture()).nodes;
  const points = new Map<string, ConstellationPoint>(nodes.map((node) => [node.id, { id: node.id, x: 450, y: 320, degree: node.id === "r" ? 4 : 0 }]));
  const first = visibleConstellationLabels(nodes, points);
  assert.deepEqual([...first], [...visibleConstellationLabels(nodes, points)]);
  assert.equal(first.size, 1);
  assert.ok(first.has("r"));
});

// --- Lenses -------------------------------------------------------------------

import { homeRoles, layout } from "../lib/constellation.ts";

function twoRoles(): Brain {
  const brain = fixture();
  brain.roles.push({ id: "r2", label: "R2", company: "Second employer", title: "Lead", start_date: null, end_date: null, level: null, responsibilities: [], source });
  brain.projects.push({ id: "p2", label: "P2", role_id: "r2", name: "Platform", problem: null, action: null, result: null, tech: [], metrics: [], source });
  // Terraform: a project in the first role, ongoing work in the second.
  brain.skills[0].role_ids = ["r2"];
  brain.skills.push({ id: "k2", label: "K2", name: "Go", depth: 2, project_ids: ["p2"], role_ids: [], source });
  return brain;
}

test("home roles follow confirmed links only", () => {
  const { nodes, edges } = buildBrainGraph(twoRoles());
  const homes = homeRoles(nodes, edges);
  assert.deepEqual(homes.get("k")?.sort(), ["r", "r2"]); // via p, and directly
  assert.deepEqual(homes.get("k2"), ["r2"]);
  assert.deepEqual(homes.get("s"), ["r"]);
  assert.equal(homes.get("a"), undefined); // the certification links to nothing
});

test("by role: a skill shared by two roles settles between them", () => {
  const { nodes, edges } = buildBrainGraph(twoRoles());
  const { positions, territories } = layout(nodes, edges, "role");
  const [r1, r2, shared, own] = ["r", "r2", "k", "k2"].map((id) => positions.get(id)!);
  const between = (v: number, a: number, b: number) => v > Math.min(a, b) && v < Math.max(a, b);
  assert.ok(between(shared.x, r1.x, r2.x), "the shared skill sits between the roles");
  assert.ok(Math.abs(own.x - r2.x) < Math.abs(own.x - r1.x), "a one-role skill stays near its role");
  assert.deepEqual(territories.map((t) => t.id).sort(), ["r", "r2"]);
});

test("by kind: one territory per kind, and layouts are deterministic", () => {
  const { nodes, edges } = buildBrainGraph(twoRoles());
  const first = layout(nodes, edges, "kind");
  assert.deepEqual(new Set(first.territories.map((t) => t.kind)), new Set(nodes.map((n) => n.kind)));
  const again = layout(nodes, edges, "kind");
  assert.deepEqual([...again.positions.values()], [...first.positions.values()]);
});
