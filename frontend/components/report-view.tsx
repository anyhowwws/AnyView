"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DIMENSION_LABELS, type DimensionScore, type Report } from "@/lib/types";

interface Props {
  report: Report;
  onRestart: () => void;
}

/** Per-dimension scores only — there is deliberately no overall number. */
export function ReportView({ report, onRestart }: Props) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Your report</h1>
          <p className="text-sm text-muted-foreground">
            {report.role} · {report.company} · {report.seniority}
          </p>
          <p className="text-xs text-muted-foreground">
            Scores and ideal answers are AI-generated from your answers and your resume. Check the
            facts before you reuse them.
          </p>
        </div>
        <Button variant="outline" className="h-10" onClick={onRestart}>
          Start another
        </Button>
      </header>

      {report.items.map((item, i) => (
        <Card key={item.question.id}>
          <CardHeader>
            <CardDescription>
              Question {i + 1} · <Badge variant="secondary">{item.question.competency}</Badge>
            </CardDescription>
            <CardTitle className="text-base leading-snug font-medium">{item.question.text}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <ul className="grid gap-3 sm:grid-cols-2">
              {item.dimensions.map((d) => (
                <ScoreRow key={d.dimension} score={d} />
              ))}
            </ul>

            <p className="text-sm">{item.summary}</p>

            <div className="grid gap-4 lg:grid-cols-2">
              <Column title="Your answer">
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{item.answer}</p>
              </Column>
              <Column title={report.source === "brain" ? "Ideal answer, from your brain" : "Ideal answer, from your resume"}>
                {item.ideal.resume_has_material ? (
                  <>
                    <p className="whitespace-pre-wrap text-sm">{item.ideal.answer}</p>
                    {item.ideal.cited_resume_lines.length > 0 && (
                      <ul className="mt-3 space-y-1 border-l-2 pl-3 text-xs text-muted-foreground">
                        {item.ideal.cited_resume_lines.map((line, j) => (
                          <li key={j}>{line}</li>
                        ))}
                      </ul>
                    )}
                  </>
                ) : (
                  <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">
                    {item.ideal.answer}
                  </p>
                )}
              </Column>
            </div>

            {item.gaps.length > 0 && (
              <div>
                <h3 className="mb-2 text-sm font-medium">Gaps</h3>
                <ul className="list-disc space-y-1 pl-5 text-sm">
                  {item.gaps.map((gap, j) => (
                    <li key={j}>{gap}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function ScoreRow({ score }: { score: DimensionScore }) {
  return (
    <li className="space-y-1">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">{DIMENSION_LABELS[score.dimension]}</span>
        <span className="tabular-nums text-muted-foreground">{score.score} / 4</span>
      </div>
      <div className="flex gap-1" aria-hidden>
        {[1, 2, 3, 4].map((n) => (
          <span
            key={n}
            className={`h-1.5 flex-1 rounded-full ${n <= score.score ? "bg-primary" : "bg-muted"}`}
          />
        ))}
      </div>
      <p className="text-sm text-muted-foreground">{score.evidence}</p>
    </li>
  );
}

function Column({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border p-4">
      <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </div>
  );
}
