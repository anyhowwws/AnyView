"use client";

import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";
import { KIND_COLORS } from "@/lib/brain-graph";
import {
  PART_KIND,
  entriesLabel,
  headline,
  partName,
  type IngestView,
  type Step,
} from "@/lib/ingest-progress";

const FILE_STEPS: { step: Step; label: string }[] = [
  { step: "upload", label: "Upload" },
  { step: "read", label: "Read" },
  { step: "parts", label: "Extract" },
  { step: "tidy", label: "Tidy" },
  { step: "link", label: "Link" },
];
const TEXT_STEPS = FILE_STEPS.slice(2);

/** Where Donna is while she reads a resume or a capture (ADR 0019). Every
 *  node is a real part of the document and lights up when that part is read:
 *  the motion reports state, it is not a loading loop. */
export function IngestProgress({ view, fromFile }: { view: IngestView; fromFile: boolean }) {
  const reduce = useReducedMotion();
  const seconds = useElapsed();
  const steps = fromFile ? FILE_STEPS : TEXT_STEPS;
  const current = steps.findIndex((s) => s.step === view.step);
  const done = view.parts.filter((p) => p.done).length;

  return (
    <section className="ingest" aria-live="polite" aria-busy="true" aria-label="Donna is reading">
      <div className="ingest-head">
        <p className="ingest-title">{headline(view)}</p>
        <span className="ingest-clock" aria-label={`${seconds} seconds so far`}>
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
        </span>
      </div>
      <p className="ingest-note">
        Each part is read on its own, then every entry is checked against your own words.
      </p>

      <ol className="ingest-steps">
        {steps.map((s, i) => {
          const state = i < current ? "done" : i === current ? "active" : "waiting";
          return (
            <li key={s.step} data-state={state}>
              <span className="ingest-step-mark" aria-hidden>
                {state === "done" ? <Check size={12} strokeWidth={2.5} /> : null}
              </span>
              <span>{s.label}</span>
              <span className="sr-only">{state === "done" ? "done" : state === "active" ? "in progress" : "waiting"}</span>
            </li>
          );
        })}
      </ol>

      {view.parts.length > 0 && (
        <>
          {view.parts.length > 1 && (
            <p className="ingest-count">
              {done} of {view.parts.length} parts read
            </p>
          )}
          <ul className="ingest-parts">
            {view.parts.map((part, i) => {
              const kind = PART_KIND[part.kind];
              const color = kind ? KIND_COLORS[kind] : "var(--primary)";
              return (
                <motion.li
                  key={part.id}
                  initial={reduce ? false : { opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.35, delay: reduce ? 0 : i * 0.05, ease: [0.16, 1, 0.3, 1] }}
                  data-done={part.done}
                >
                  <span className="ingest-node" style={{ ["--node" as string]: color }} aria-hidden>
                    {!part.done && !reduce && (
                      <motion.span
                        className="ingest-node-pulse"
                        animate={{ scale: [1, 1.9], opacity: [0.5, 0] }}
                        transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut", delay: (i % 4) * 0.3 }}
                      />
                    )}
                    <motion.span
                      className="ingest-node-core"
                      initial={false}
                      animate={{ scale: part.done ? 1 : 0.55 }}
                      transition={{ type: "spring", stiffness: 320, damping: 18 }}
                    />
                  </span>
                  <span className="ingest-part-name">{partName(part)}</span>
                  <span className="ingest-part-state">
                    {part.done ? entriesLabel(part.found ?? 0) : "Reading"}
                  </span>
                  {part.names.length > 0 && (
                    // What this part found, arriving while the others are still read.
                    <ul className="ingest-found" aria-label={`Found in ${partName(part)}`}>
                      {part.names.map((name, n) => (
                        <motion.li
                          key={name}
                          initial={reduce ? false : { opacity: 0, x: -4 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ duration: 0.3, delay: reduce ? 0 : n * 0.06, ease: [0.16, 1, 0.3, 1] }}
                        >
                          {name}
                        </motion.li>
                      ))}
                      {(part.found ?? 0) > part.names.length && (
                        <li className="ingest-found-more">and {(part.found ?? 0) - part.names.length} more</li>
                      )}
                    </ul>
                  )}
                </motion.li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

/** Whole seconds since the view mounted. A 1 Hz tick: nothing here moves faster. */
function useElapsed(): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}
