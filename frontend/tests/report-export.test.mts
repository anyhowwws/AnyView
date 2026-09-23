import assert from "node:assert/strict";
import { test } from "node:test";
import { reportFilename, reportToMarkdown } from "../lib/report-export.ts";
import type { Report } from "../lib/types.ts";

const LABELS = {
  difficulty: "Hiring manager",
  dimensions: {
    star_completeness: "STAR completeness",
    specificity: "Specificity",
    quantified_outcome: "Quantified outcome",
    ownership_language: "Ownership language",
  },
};

const DATE = new Date(2026, 8, 24, 21, 30); // local evening: must still be the 24th

function report(overrides: Partial<Report> = {}): Report {
  return {
    session_id: "s1",
    company: "Initech",
    role: "Cloud Architect",
    seniority: "senior",
    difficulty: "hiring_manager",
    garden_used: false,
    items: [
      {
        question: { id: 1, text: "Tell me about yourself.", competency: "communication", rationale: "Opener", seconds: 90 },
        answer: "I build platforms.\nMostly on GCP.",
        dimensions: [
          { dimension: "specificity", score: 2, evidence: "Names GCP | but\nno numbers" },
        ],
        summary: "Clear but thin.",
        gaps: ["No outcome"],
        ideal: { answer: "Lead with the migration.", cited_lines: ["Led migration of 40 services"], has_material: true },
      },
    ],
    ...overrides,
  };
}

test("filename is a lowercase slug of company, role and local date", () => {
  assert.equal(reportFilename(report(), DATE), "anyview-initech-cloud-architect-2026-09-24.md");
  assert.equal(reportFilename(report({ company: "", role: "!!" }), DATE), "anyview-interview-2026-09-24.md");
});

test("markdown carries every section of the report", () => {
  const md = reportToMarkdown(report(), LABELS, DATE);
  assert.match(md, /^# Interview report — Cloud Architect, Initech/);
  assert.match(md, /- Difficulty: Hiring manager/);
  assert.match(md, /## Question 1 · communication/);
  assert.match(md, /> I build platforms\.\n> Mostly on GCP\./);
  assert.match(md, /\| Specificity \| 2 \/ 4 \| Names GCP \\\| but no numbers \|/);
  assert.match(md, /### Ideal answer \(resume\)\n\nLead with the migration\./);
  assert.match(md, /- Led migration of 40 services/);
  assert.match(md, /### Gaps\n\n- No outcome/);
  assert.doesNotMatch(md, /Digital Garden/);
});

test("an ideal answer without material is shown as the model's caveat, not an answer", () => {
  const r = report({ garden_used: true });
  r.items[0].ideal = { answer: "Your resume has nothing on this.", cited_lines: [], has_material: false };
  const md = reportToMarkdown(r, LABELS, DATE);
  assert.match(md, /### Ideal answer \(resume and Digital Garden\)\n\n_Your resume has nothing on this\._/);
  assert.doesNotMatch(md, /Drawn from/);
});
