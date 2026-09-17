"use client";

import type { Coverage, Strength } from "@/lib/types";

const CELL: Record<Strength, string> = {
  none: "bg-muted",
  weak: "bg-primary/35",
  strong: "bg-primary",
};
const WORD: Record<Strength, string> = { none: "no evidence", weak: "weak evidence", strong: "strong evidence" };

/** competency × role. The hero of the Brain screen: what the brain can and
 *  cannot answer for. Colour is doubled by the cell's accessible label. */
export function CoverageHeatmap({ coverage }: { coverage: Coverage }) {
  const columns = [...coverage.roles.map((r) => ({ id: r.id, label: r.company })), { id: "other", label: "Other" }];
  const hasOther = coverage.competencies.some((c) => coverage.cells[c.key]?.other !== "none");
  const cols = hasOther || coverage.roles.length === 0 ? columns : columns.slice(0, -1);
  const total = coverage.competencies.length * cols.length;
  const strong = coverage.competencies.reduce(
    (n, c) => n + cols.filter((col) => coverage.cells[c.key]?.[col.id] === "strong").length,
    0,
  );

  return (
    <section aria-labelledby="coverage-heading" className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="coverage-heading" className="text-lg font-semibold tracking-tight">
          Coverage
        </h2>
        <p className="text-xs text-muted-foreground">
          {strong} of {total} competency × role cells have a story with a result
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-1 text-sm">
          <thead>
            <tr>
              <th scope="col" className="sr-only">
                Competency
              </th>
              {cols.map((c) => (
                <th key={c.id} scope="col" className="max-w-24 truncate px-1 pb-1 text-left text-xs font-medium text-muted-foreground">
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {coverage.competencies.map((comp) => (
              <tr key={comp.key}>
                <th scope="row" className="w-36 pr-2 text-left text-xs font-medium">
                  {comp.label}
                </th>
                {cols.map((col) => {
                  const s = coverage.cells[comp.key]?.[col.id] ?? "none";
                  return (
                    <td key={col.id} className="p-0">
                      <div
                        role="img"
                        aria-label={`${comp.label} at ${col.label}: ${WORD[s]}`}
                        title={`${comp.label} · ${col.label}: ${WORD[s]}`}
                        className={`h-7 rounded ${CELL[s]}`}
                      />
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden>
        <span className="inline-flex items-center gap-1"><i className={`inline-block size-3 rounded ${CELL.none}`} /> none</span>
        <span className="inline-flex items-center gap-1"><i className={`inline-block size-3 rounded ${CELL.weak}`} /> story, no result</span>
        <span className="inline-flex items-center gap-1"><i className={`inline-block size-3 rounded ${CELL.strong}`} /> story with a result</span>
      </p>
    </section>
  );
}
