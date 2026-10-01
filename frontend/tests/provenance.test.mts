import assert from "node:assert/strict";
import { test } from "node:test";
import { findQuote, originLine } from "../lib/provenance.ts";

test("the origin line names the source and its date", () => {
  assert.equal(originLine({ raw_dump_id: "d", event_id: 1, origin: "resume", added_on: "2026-10-02T09:00:00Z" }), "From your resume · 2 Oct 2026");
  assert.equal(originLine({ raw_dump_id: "d", event_id: 1, origin: "manual" }), "Added by hand");
  assert.equal(originLine({ raw_dump_id: "d", event_id: 1 }), "Source");
});

test("a quote is found across the line breaks an extracted PDF adds", () => {
  const text = "Education\nNanyang Technological University —\nB.Sc. (Hons)  Mathematical Sciences";
  const at = findQuote(text, "nanyang technological university — B.Sc. (Hons) Mathematical");
  assert.ok(at);
  assert.equal(text.slice(...at), "Nanyang Technological University —\nB.Sc. (Hons)  Mathematical");
  assert.equal(findQuote(text, "Stanford"), null);
  assert.equal(findQuote(text, ""), null);
});
