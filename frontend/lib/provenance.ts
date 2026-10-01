// How a garden card says where its entry came from (ADR 0023): one quiet
// line, the quote behind it on request, the whole document only if asked.

import type { Provenance } from "./types";

const FROM: Record<NonNullable<Provenance["origin"]>, string> = {
  resume: "From your resume",
  file: "From an uploaded file",
  capture: "From a capture",
  manual: "Added by hand",
};

/** "From your resume · 2 Oct 2026". */
export function originLine(source: Provenance): string {
  const from = source.origin ? FROM[source.origin] : "Source";
  if (!source.added_on) return from;
  const when = new Date(source.added_on).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  return `${from} · ${when}`;
}

/** Where the quote sits in the document, as [start, end), or null. Matching
 *  ignores case and how whitespace was laid out, since an extracted PDF
 *  breaks lines where the quote does not. */
export function findQuote(text: string, quote: string | null | undefined): [number, number] | null {
  const words = (quote ?? "").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return null;
  const escape = (w: string) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(words.map(escape).join("\\s+"), "i").exec(text);
  return match ? [match.index, match.index + match[0].length] : null;
}
