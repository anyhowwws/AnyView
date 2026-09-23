// Donna's Discover answers are short Markdown with [P3]-style citations
// (ADR 0017). This turns them into blocks the panel renders, without a
// Markdown library: the prompt only asks for paragraphs, lists and bold, so
// that is all this reads. Anything else shows as plain text.

import type { Brain, Coverage } from "./types";

export type Inline =
  | { t: "text"; text: string }
  | { t: "bold"; text: string }
  | { t: "cite"; label: string };

export type Block =
  | { type: "p"; inline: Inline[] }
  | { type: "ul" | "ol"; items: Inline[][] };

const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

/** Split one line into text, **bold** and citation pieces. A label becomes a
 *  citation only if the server resolved it (`known`); an invented [P9] stays
 *  as the text the model wrote. */
export function inline(line: string, known: Set<string>): Inline[] {
  const out: Inline[] = [];
  const pattern = /\*\*(.+?)\*\*|\[([A-Z]\d+(?:\s*,\s*[A-Z]\d+)*)\]/g;
  let last = 0;
  for (const m of line.matchAll(pattern)) {
    const at = m.index ?? 0;
    if (m[2] !== undefined) {
      const labels = m[2].split(",").map((l) => l.trim());
      if (!labels.every((l) => known.has(l))) continue; // leave it in the text run
      if (at > last) out.push({ t: "text", text: line.slice(last, at) });
      for (const label of labels) out.push({ t: "cite", label });
    } else {
      if (at > last) out.push({ t: "text", text: line.slice(last, at) });
      out.push({ t: "bold", text: m[1] });
    }
    last = at + m[0].length;
  }
  if (last < line.length) out.push({ t: "text", text: line.slice(last) });
  return out;
}

export function blocks(text: string, known: Set<string>): Block[] {
  const out: Block[] = [];
  let para: string[] = [];
  const flush = () => {
    if (para.length) out.push({ type: "p", inline: inline(para.join(" "), known) });
    para = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const kind = BULLET.test(line) ? "ul" : NUMBERED.test(line) ? "ol" : null;
    if (kind) {
      flush();
      const item = inline(line.replace(kind === "ul" ? BULLET : NUMBERED, ""), known);
      const prev = out[out.length - 1];
      if (prev && prev.type === kind) prev.items.push(item);
      else out.push({ type: kind, items: [item] });
    } else if (line.trim() === "") {
      flush();
    } else {
      para.push(line.trim());
    }
  }
  flush();
  return out;
}

/** Starter questions: one about the strongest skill, then the competencies
 *  no role covers — the gaps worth asking about before an interview. */
export function suggestions(brain: Brain, limit = 4): string[] {
  const out: string[] = [];
  const skill = [...brain.skills].sort((a, b) => b.depth - a.depth)[0];
  if (skill) out.push(`Which projects have I done with ${skill.name}?`);
  if (brain.stories.length) out.push("Which stories show ownership best?");
  for (const c of gaps(brain.coverage)) out.push(`Do I have anything for ${c.toLowerCase()}?`);
  out.push("What should I add to my garden next?");
  return out.slice(0, limit);
}

function gaps(coverage: Coverage): string[] {
  return coverage.competencies
    .filter((c) => Object.values(coverage.cells[c.key] ?? {}).every((s) => s === "none"))
    .map((c) => c.label);
}
