"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Download, Printer } from "lucide-react";
import { downloadText, reportFilename, reportToMarkdown } from "@/lib/report-export";
import {
  DIFFICULTIES,
  DIMENSION_LABELS,
  type Dimension,
  type DimensionScore,
  type Question,
  type QuestionReport,
  type Report,
} from "@/lib/types";

/** One question's place in the report. `result` is null while it is still
 *  being scored; the question and your answer are known before that. */
export interface Slot {
  question: Question;
  answer: string;
  result: QuestionReport | null;
}

interface Props {
  header: Omit<Report, "items">;
  slots: Slot[];
  onRestart: () => void;
  /** Set while scoring failed part-way: the message and a way to try again. */
  error?: string | null;
  onRetry?: () => void;
}

/** Per-dimension scores only — there is deliberately no overall number.
 *  The report fills in as each question is scored (they finish in any
 *  order), so the cards still waiting show your answer beside a placeholder. */
export function ReportView({ header, slots, onRestart, error, onRetry }: Props) {
  const difficulty = DIFFICULTIES.find((d) => d.value === header.difficulty)?.label ?? header.difficulty;
  const scored = slots.filter((s) => s.result !== null).length;
  const complete = scored === slots.length;

  function downloadMarkdown() {
    if (!complete) return;
    const full: Report = { ...header, items: slots.map((s) => s.result as QuestionReport) };
    const now = new Date();
    const md = reportToMarkdown(full, { difficulty, dimensions: DIMENSION_LABELS }, now);
    downloadText(reportFilename(full, now), md);
  }

  return (
    <div className="report-view mx-auto flex w-full max-w-4xl flex-col gap-6">
      <header className="page-heading">
        <div className="space-y-1">
          <p className="eyebrow">A clearer picture of your strengths</p>
          <h1>Your next step<span className="text-primary">.</span></h1>
          <p className="text-sm text-muted-foreground">
            {header.role} · {header.company} · {header.seniority} · {difficulty}
          </p>
          <p className="text-xs text-muted-foreground">
            Scores and ideal answers are AI-generated from your answers, your resume
            {header.garden_used && " and your Digital Garden"}. Check the facts before you
            reuse them.
          </p>
        </div>
        {/* print:hidden — the saved PDF is the report, not the controls around it. */}
        <div className="flex flex-wrap gap-2 print:hidden">
          <Button variant="outline" className="h-10" onClick={downloadMarkdown} disabled={!complete}>
            <Download aria-hidden /> Download (.md)
          </Button>
          <Button variant="outline" className="h-10" onClick={() => window.print()} disabled={!complete}>
            <Printer aria-hidden /> Save as PDF
          </Button>
          <Button variant="outline" className="h-10" onClick={onRestart}>
            Start another
          </Button>
        </div>
      </header>

      {!complete && <ScoringStatus scored={scored} total={slots.length} error={error} onRetry={onRetry} />}

      {slots.map((slot, i) => (
        <Card key={slot.question.id}>
          <CardHeader>
            <CardDescription>
              Question {i + 1} · <Badge variant="secondary">{slot.question.competency}</Badge>
            </CardDescription>
            <CardTitle className="text-base leading-snug font-medium">{slot.question.text}</CardTitle>
          </CardHeader>
          {slot.result ? (
            <Scored item={slot.result} gardenUsed={header.garden_used} />
          ) : (
            <Waiting answer={slot.answer} failed={Boolean(error)} />
          )}
        </Card>
      ))}
    </div>
  );
}

/** A scored question. It fades in when it lands, so the change is noticed. */
function Scored({ item, gardenUsed }: { item: QuestionReport; gardenUsed: boolean }) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
    >
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
          <Column
            title={
              gardenUsed
                ? "Ideal answer, from your resume and Digital Garden"
                : "Ideal answer, from your resume"
            }
          >
            {item.ideal.has_material ? (
              <>
                <p className="whitespace-pre-wrap text-sm">{item.ideal.answer}</p>
                {item.ideal.cited_lines.length > 0 && (
                  <ul className="mt-3 space-y-1 border-l-2 pl-3 text-xs text-muted-foreground">
                    {item.ideal.cited_lines.map((line: string, j: number) => (
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
    </motion.div>
  );
}

const DIMENSIONS = Object.keys(DIMENSION_LABELS) as Dimension[];

/** A question still being scored: your answer is real, the rest is a placeholder
 *  in the shape of what is coming. */
function Waiting({ answer, failed }: { answer: string; failed: boolean }) {
  const pulse = failed ? "" : "animate-pulse motion-reduce:animate-none";
  return (
    <CardContent className="space-y-6" aria-busy={!failed}>
      <ul className="grid gap-3 sm:grid-cols-2" aria-hidden>
        {DIMENSIONS.map((d) => (
          <li key={d} className="space-y-1">
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-medium text-muted-foreground">{DIMENSION_LABELS[d]}</span>
              <span className="text-muted-foreground">– / 4</span>
            </div>
            <div className="flex gap-1">
              {[1, 2, 3, 4].map((n) => (
                <span key={n} className={`h-1.5 flex-1 rounded-full bg-muted ${pulse}`} />
              ))}
            </div>
          </li>
        ))}
      </ul>
      <p className="text-sm text-muted-foreground">
        {failed ? "Not scored." : "Scoring this answer and writing an ideal one…"}
      </p>
      <div className="grid gap-4 lg:grid-cols-2">
        <Column title="Your answer">
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{answer}</p>
        </Column>
        <Column title="Ideal answer">
          <div className="space-y-2" aria-hidden>
            {["w-full", "w-11/12", "w-4/5", "w-2/3"].map((w) => (
              <span key={w} className={`block h-3 rounded bg-muted ${w} ${pulse}`} />
            ))}
          </div>
        </Column>
      </div>
    </CardContent>
  );
}

/** How far scoring has got. A count, not a spinner: each question appears
 *  below as soon as it is done. */
function ScoringStatus({
  scored,
  total,
  error,
  onRetry,
}: {
  scored: number;
  total: number;
  error?: string | null;
  onRetry?: () => void;
}) {
  const seconds = useElapsed();
  if (error) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/40 p-4 text-sm print:hidden">
        <p className="text-destructive" role="alert">{error}</p>
        {onRetry && (
          <button className="underline underline-offset-4" onClick={onRetry}>
            Try again
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-2 rounded-lg border p-4 print:hidden" role="status">
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span>
          Scoring your answers against the rubric: <span className="tabular-nums">{scored} of {total}</span> done
        </span>
        <span className="tabular-nums text-muted-foreground">{seconds} s</span>
      </div>
      <div className="flex gap-1" aria-hidden>
        {Array.from({ length: total }, (_, i) => (
          <span
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-500 ${i < scored ? "bg-primary" : "bg-muted"}`}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        Each question appears below as soon as it is marked. Read your answers while you wait.
      </p>
    </div>
  );
}

function useElapsed(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
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
