import assert from "node:assert/strict";
import { test } from "node:test";
import { buildBrainGraph } from "../lib/brain-graph.ts";
import type { Brain } from "../lib/types.ts";

const source = { raw_dump_id: "dump", event_id: 1 };
function fixture(): Brain {
  return {
    roles: [{ id: "r", label: "R1", company: "Test employer", title: "Architect", start_date: null, end_date: null, level: null, source }],
    projects: [{ id: "p", label: "P1", role_id: "r", name: "Migration", problem: null, action: null, result: "Reduced costs", tech: [], metrics: [], source }],
    stories: [{ id: "s", label: "S1", role_id: "r", project_id: "p", title: "Cutover", situation: null, task: null, action: null, result: null, competencies: [], source }],
    skills: [{ id: "k", label: "K1", name: "Terraform", depth: 4, project_ids: ["p"], source }],
    achievements: [{ id: "a", label: "A1", title: "Certification", kind: "credential", issuer: null, achieved_on: null, source }],
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

test("does not draw links to retired or missing entities", () => {
  const brain = fixture();
  brain.roles = [];
  brain.projects = [];
  assert.deepEqual(buildBrainGraph(brain).edges, []);
});

test("empty brain has no synthetic nodes or edges", () => {
  const brain = fixture();
  brain.roles = []; brain.projects = []; brain.stories = []; brain.skills = []; brain.achievements = [];
  assert.deepEqual(buildBrainGraph(brain), { nodes: [], edges: [] });
});
