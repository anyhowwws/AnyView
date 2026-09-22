import assert from "node:assert/strict";
import { test } from "node:test";
import {
  EMPTY_JOB,
  formatJob,
  jobIsDescribed,
  valuesFromParse,
} from "../lib/job-template.ts";

test("folds the filled-in fields into something that reads like a posting", () => {
  assert.equal(
    formatJob("Cloud Architect", "Initech", {
      team: "Platform Engineering",
      responsibilities: "Own the platform roadmap\n- Set the guardrails",
      must_haves: "Terraform\n\nStrong communication",
      nice_to_haves: "",
    }),
    "Cloud Architect — Initech\n\n" +
      "Team: Platform Engineering\n\n" +
      "Responsibilities:\n- Own the platform roadmap\n- Set the guardrails\n\n" +
      "Must-haves:\n- Terraform\n- Strong communication",
  );
});

test("leaves out every section the user did not fill in", () => {
  assert.equal(formatJob("Cloud Architect", "", EMPTY_JOB), "Cloud Architect");
  assert.equal(formatJob("", "", EMPTY_JOB), "");
});

test("a posting is described once it says what the work is or what it needs", () => {
  assert.equal(jobIsDescribed(EMPTY_JOB), false);
  assert.equal(jobIsDescribed({ ...EMPTY_JOB, team: "Platform" }), false);
  assert.equal(jobIsDescribed({ ...EMPTY_JOB, must_haves: "Terraform" }), true);
  assert.equal(jobIsDescribed({ ...EMPTY_JOB, responsibilities: "  \n \n" }), false);
});

test("an uploaded JD's parse pours into the same fields the manual path fills", () => {
  assert.deepEqual(
    valuesFromParse({
      company: "Initech",
      role: "Cloud Architect",
      seniority: "senior",
      responsibilities: ["Own the platform roadmap"],
      must_haves: ["Terraform", "Strong communication"],
      nice_to_haves: [],
    }),
    {
      team: "",
      responsibilities: "Own the platform roadmap",
      must_haves: "Terraform\nStrong communication",
      nice_to_haves: "",
    },
  );
});
