// The report as a file the candidate keeps. Everything happens in the browser:
// the report is already here (the session is stateless server-side), so there
// is no endpoint to add and nothing new to store. Markdown because it is plain
// text — it opens anywhere, diffs between attempts, and pastes into notes.
// PDF is the browser's own "Save as PDF" over a print stylesheet, not a library.
//
// Labels come in as an argument rather than being imported from types.ts, so
// this file only has type imports and the node test runner can load it as-is.
import type { Dimension, Report } from "./types";

export interface ExportLabels {
  difficulty: string;
  dimensions: Record<Dimension, string>;
}

/** "anyview-initech-cloud-architect-2026-09-24.md" — safe on every filesystem. */
export function reportFilename(report: Report, date: Date): string {
  const slug = `${report.company} ${report.role}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `anyview-${slug || "interview"}-${isoDate(date)}.md`;
}

export function reportToMarkdown(report: Report, labels: ExportLabels, date: Date): string {
  const garden = report.garden_used ? " and your Digital Garden" : "";
  const out: string[] = [
    `# Interview report — ${report.role}, ${report.company}`,
    "",
    `- Date: ${isoDate(date)}`,
    `- Seniority: ${report.seniority}`,
    `- Difficulty: ${labels.difficulty}`,
    "",
    `> Scores and ideal answers are AI-generated from your answers, your resume${garden}. ` +
      "Check the facts before you reuse them. Scores are per dimension, out of 4; " +
      "there is deliberately no overall number.",
  ];

  report.items.forEach((item, i) => {
    out.push("", "---", "", `## Question ${i + 1} · ${item.question.competency}`, "", quote(item.question.text));

    out.push("", "### Scores", "", "| Dimension | Score | Evidence |", "|---|---|---|");
    for (const d of item.dimensions) {
      out.push(`| ${labels.dimensions[d.dimension]} | ${d.score} / 4 | ${cell(d.evidence)} |`);
    }

    out.push("", "### Summary", "", item.summary);
    out.push("", "### Your answer", "", quote(item.answer));

    out.push("", report.garden_used ? "### Ideal answer (resume and Digital Garden)" : "### Ideal answer (resume)", "");
    if (item.ideal.has_material) {
      out.push(item.ideal.answer);
      if (item.ideal.cited_lines.length > 0) {
        out.push("", "Drawn from:", "", ...item.ideal.cited_lines.map((l) => `- ${l}`));
      }
    } else {
      out.push(`_${item.ideal.answer}_`);
    }

    if (item.gaps.length > 0) {
      out.push("", "### Gaps", "", ...item.gaps.map((g) => `- ${g}`));
    }
  });

  return out.join("\n") + "\n";
}

/** Hand a string to the browser as a download. The object URL is revoked on
 *  the next tick — after the click has started the download, not before. */
export function downloadText(filename: string, text: string, type = "text/markdown"): void {
  const url = URL.createObjectURL(new Blob([text], { type: `${type};charset=utf-8` }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function isoDate(date: Date): string {
  // Local date, not toISOString(), which is UTC and can be "tomorrow" in the evening.
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Multi-line text as a blockquote; every line needs its own ">". */
function quote(text: string): string {
  return text.split("\n").map((l) => `> ${l}`).join("\n");
}

/** A table cell can't hold a newline or an unescaped pipe. */
function cell(text: string): string {
  return text.replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ");
}
