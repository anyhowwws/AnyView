import assert from "node:assert/strict";
import { test } from "node:test";
import { applyProgress, entriesLabel, headline, partName, startView, viewOfJob } from "../lib/ingest-progress.ts";

test("an upload walks upload → read → parts → tidy → link, naming what it is doing", () => {
  let view = startView(true);
  assert.equal(headline(view), "Uploading your file");
  view = applyProgress(view, { stage: "reading", file: "pdf" });
  assert.equal(headline(view), "Reading your document");
  view = applyProgress(view, { stage: "read", characters: 5415 });
  view = applyProgress(view, {
    stage: "sections",
    sections: [
      { id: 0, kind: "experience", label: "Multi-Cloud Solutions Architect" },
      { id: 1, kind: "certifications", label: "" },
    ],
  });
  assert.equal(view.step, "parts");
  assert.equal(headline(view), "Reading 2 parts at once");
  assert.deepEqual(view.parts.map(partName), ["Multi-Cloud Solutions Architect", "Certifications"]);
  view = applyProgress(view, { stage: "section_done", id: 1, found: 14, names: ["AWS Certified Security - Specialty"] });
  assert.deepEqual(view.parts.map((p) => [p.done, p.found]), [[false, null], [true, 14]]);
  assert.deepEqual(view.parts.map((p) => p.names), [[], ["AWS Certified Security - Specialty"]]);
  view = applyProgress(view, { stage: "section_done", id: 0, found: 9 });
  assert.equal(headline(view), "Putting the pieces together");
  view = applyProgress(view, { stage: "tidying", skills: 52 });
  assert.equal(headline(view), "Folding duplicate skills together");
  view = applyProgress(view, { stage: "linking", skills: 50 });
  assert.equal(headline(view), "Linking skills to where you used them");
  assert.equal(view.characters, 5415);
});

test("a typed capture starts in the queue and reads as one part", () => {
  let view = startView(false);
  assert.equal(view.step, "queue");
  assert.equal(headline(view), "Handing it to Donna");
  view = applyProgress(view, { stage: "sections", sections: [{ id: 0, kind: "document", label: "" }] });
  assert.equal(headline(view), "Reading what you wrote");
  assert.equal(partName(view.parts[0]), "Your text");
});

test("an unknown stage from a newer API leaves the view as it was", () => {
  const view = startView(false);
  assert.deepEqual(applyProgress(view, { stage: "someday" } as never), view);
  assert.equal(entriesLabel(1), "1 entry");
  assert.equal(entriesLabel(0), "0 entries");
});

test("a polled job's frames rebuild the same view the stream used to build", () => {
  assert.equal(viewOfJob([]).step, "queue"); // waiting for the worker
  const frames = [
    { stage: "reading", file: "pdf" },
    { stage: "read", characters: 812 },
    { stage: "sections", sections: [{ id: 0, kind: "document", label: "" }] },
    { stage: "section_done", id: 0, found: 3, names: ["Acme Corp"] },
  ] as const;
  const view = viewOfJob([...frames]);
  assert.equal(view.step, "parts");
  assert.equal(view.characters, 812);
  assert.deepEqual(view.parts.map((p) => [p.done, p.found]), [[true, 3]]);
  // A retry on the worker sends its frames from the start again.
  assert.deepEqual(viewOfJob([frames[0]]).parts, []);
});
