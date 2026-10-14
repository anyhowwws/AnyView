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

// One cited item: a label ("P3") or a range of one kind ("A1–A11", "A1-11").
// The prompt asks for one label per bracket, but the model writes ranges for a
// long run of certificates. Same grammar as the server's `discover.cited`.
const ITEM = String.raw`[A-Z]\d+(?:\s*[-–—]\s*[A-Z]?\d+)?`;
const RANGE = /^([A-Z])(\d+)\s*[-–—]\s*([A-Z]?)(\d+)$/;
const MAX_RANGE = 100;

/** The labels inside one bracket, ranges spelled out: "A1–A3, A7" gives
 *  A1, A2, A3, A7. A range across kinds or backwards keeps its first label. */
export function groupLabels(group: string): string[] {
  const out: string[] = [];
  for (const part of group.split(",").map((p) => p.trim())) {
    const m = RANGE.exec(part);
    if (!m) {
      out.push(part);
      continue;
    }
    const [, prefix, from, endPrefix, to] = m;
    const start = Number(from);
    const end = Number(to);
    if ((endPrefix === "" || endPrefix === prefix) && start <= end && end - start < MAX_RANGE) {
      for (let n = start; n <= end; n++) out.push(`${prefix}${n}`);
    } else {
      out.push(`${prefix}${start}`);
    }
  }
  return out;
}

/** Split one line into text, **bold** and citation pieces. A label becomes a
 *  citation only if the server resolved it (`known`); a bracket with no real
 *  label in it ([P9]) stays as the text the model wrote. In a bracket with
 *  some real labels, the invented ones are dropped, as the server drops them
 *  from the sources. */
export function inline(line: string, known: Set<string>): Inline[] {
  const out: Inline[] = [];
  const pattern = new RegExp(String.raw`\*\*(.+?)\*\*|\[(${ITEM}(?:\s*,\s*${ITEM})*)\]`, "g");
  let last = 0;
  for (const m of line.matchAll(pattern)) {
    const at = m.index ?? 0;
    if (m[2] !== undefined) {
      const labels = groupLabels(m[2]).filter((l) => known.has(l));
      if (labels.length === 0) continue; // leave it in the text run
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
