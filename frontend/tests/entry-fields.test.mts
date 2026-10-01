import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ENTRY_FIELDS,
  dateForMonth,
  fromFormValue,
  monthLabel,
  monthOf,
  validateEntry,
} from "../lib/entry-fields.ts";

const NOW = new Date(2026, 9, 2); // Oct 2026

test("months read, label and store at the precision a resume has", () => {
  assert.equal(monthOf("2017-08-01"), "2017-08");
  assert.equal(monthOf("2017-13-01"), "");
  assert.equal(monthOf(null), "");
  assert.equal(monthLabel("2021-04-01"), "Apr 2021");
  assert.equal(dateForMonth("2017-09", "2017-08-15"), "2017-09-01");
  // Re-picking the same month keeps a real day the entry already had.
  assert.equal(dateForMonth("2017-08", "2017-08-15"), "2017-08-15");
  assert.equal(dateForMonth("", "2017-08-15"), "");
});

test("an end before its start is reported on the end field", () => {
  const specs = ENTRY_FIELDS.education;
  const errors = validateEntry(specs, { institution: "NTU", start_date: "2021-04-01", end_date: "2017-08-01" }, NOW);
  assert.deepEqual(Object.keys(errors), ["end_date"]);
  assert.match(errors.end_date, /Apr 2021/);
  assert.deepEqual(validateEntry(specs, { institution: "NTU", start_date: "2017-08-01", end_date: "2021-04-01" }, NOW), {});
  // An open end ("Ongoing") is fine.
  assert.deepEqual(validateEntry(specs, { institution: "NTU", start_date: "2017-08-01" }, NOW), {});
});

test("required, length, depth and not-in-the-future are checked like the API does", () => {
  assert.deepEqual(Object.keys(validateEntry(ENTRY_FIELDS.role, { company: " ", title: "x" }, NOW)), ["company"]);
  assert.match(validateEntry(ENTRY_FIELDS.language, { name: "x".repeat(101) }, NOW).name, /100/);
  assert.ok(validateEntry(ENTRY_FIELDS.skill, { name: "Go", depth: "9" }, NOW).depth);
  assert.ok(validateEntry(ENTRY_FIELDS.achievement, { title: "PCA", kind: "credential", achieved_on: "2027-01-01" }, NOW).achieved_on);
  assert.deepEqual(validateEntry(ENTRY_FIELDS.achievement, { title: "PCA", kind: "credential", achieved_on: "2026-10-01" }, NOW), {});
});

test("form text goes back to the shapes the API stores", () => {
  const [, , , , , responsibilities] = ENTRY_FIELDS.role;
  assert.deepEqual(fromFormValue(responsibilities, " On-call \n\n Hiring "), ["On-call", "Hiring"]);
  assert.equal(fromFormValue(ENTRY_FIELDS.role[2], "  "), null);
  assert.equal(fromFormValue(ENTRY_FIELDS.skill[1], "4"), 4);
});
