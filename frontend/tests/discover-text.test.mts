import assert from "node:assert/strict";
import { test } from "node:test";
import { blocks, groupLabels, inline, suggestions } from "../lib/discover-text.ts";
import type { Brain } from "../lib/types.ts";

const known = new Set(["P1", "S1"]);

test("resolved labels become citations; invented ones stay text", () => {
  assert.deepEqual(inline("The migration [P1] and [P9].", known), [
    { t: "text", text: "The migration " },
    { t: "cite", label: "P1" },
    { t: "text", text: " and [P9]." },
  ]);
});

test("a comma list of labels becomes one citation each", () => {
  assert.deepEqual(inline("[P1, S1]", known), [{ t: "cite", label: "P1" }, { t: "cite", label: "S1" }]);
});

test("a range of labels becomes one citation per label", () => {
  const certs = new Set(["A1", "A2", "A3", "A5"]);
  assert.deepEqual(inline("certifications [A1–A3, A5].", certs), [
    { t: "text", text: "certifications " },
    { t: "cite", label: "A1" },
    { t: "cite", label: "A2" },
    { t: "cite", label: "A3" },
    { t: "cite", label: "A5" },
    { t: "text", text: "." },
  ]);
});

test("ranges: hyphens, a bare end number, and nonsense kept to the first label", () => {
  assert.deepEqual(groupLabels("A1-3"), ["A1", "A2", "A3"]);
  assert.deepEqual(groupLabels("A1 — A2, P4"), ["A1", "A2", "P4"]);
  assert.deepEqual(groupLabels("A5–A2"), ["A5"]);
  assert.deepEqual(groupLabels("A1–P3"), ["A1"]);
});

test("invented labels in a bracket with real ones are dropped", () => {
  assert.deepEqual(inline("[P1, P9]", known), [{ t: "cite", label: "P1" }]);
});

test("bold, paragraphs and both list kinds", () => {
  const out = blocks("You have **two**:\n\n- one [P1]\n- two [S1]\n\n1. first\n2. second\nDone.", known);
  assert.deepEqual(out.map((b) => b.type), ["p", "ul", "ol", "p"]);
  assert.deepEqual(out[0], { type: "p", inline: [{ t: "text", text: "You have " }, { t: "bold", text: "two" }, { t: "text", text: ":" }] });
  assert.equal(out[1].type === "ul" && out[1].items.length, 2);
});

test("suggestions lead with the deepest skill and name uncovered competencies", () => {
  const source = { raw_dump_id: "d", event_id: 1 };
  const brain: Brain = {
    roles: [], projects: [], stories: [], achievements: [], education: [], languages: [], feedback: [],
    skills: [
      { id: "k1", label: "K1", name: "Terraform", depth: 3, project_ids: [], source },
      { id: "k2", label: "K2", name: "Bedrock", depth: 5, project_ids: [], source },
    ],
    coverage: {
      competencies: [{ key: "conflict", label: "Conflict" }, { key: "ownership", label: "Ownership" }],
      roles: [],
      cells: { conflict: { r: "none" }, ownership: { r: "strong" } },
    },
    pending_proposals: 0,
  };
  assert.deepEqual(suggestions(brain), [
    "Which projects have I done with Bedrock?",
    "Do I have anything for conflict?",
    "What should I add to my garden next?",
  ]);
});
