"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Popover } from "@base-ui/react/popover";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  DEPTHS,
  MONTHS,
  asFormValue,
  dateForMonth,
  fromFormValue,
  monthLabel,
  monthOf,
  thisMonth,
  validateEntry,
  type FieldSpec,
} from "@/lib/entry-fields";

// Shared by the in-place editor, the add form and the review queue, so every
// garden field has a visible label, says when it is required, explains
// itself where that helps, and reports a problem next to the field itself.

const CONTROL =
  "h-10 w-full rounded-lg border border-input bg-transparent px-3 text-sm outline-none transition-colors " +
  "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 " +
  "aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 dark:bg-input/30";

type Values = Record<string, string>;

/** A grid of labelled fields. Controlled: the caller owns the values and
 *  decides which errors are showing. */
export function EntryFields({
  specs,
  values,
  errors = {},
  disabled,
  onChange,
  onBlur,
}: {
  specs: FieldSpec[];
  values: Values;
  errors?: Record<string, string>;
  disabled?: boolean;
  onChange: (name: string, value: string) => void;
  onBlur?: (name: string) => void;
}) {
  const base = useId();
  const now = thisMonth();
  return (
    <div className="grid gap-x-3 gap-y-4 sm:grid-cols-2">
      {specs.map((spec) => {
        const id = `${base}-${spec.name}`;
        const value = values[spec.name] ?? "";
        const error = errors[spec.name];
        const hintId = spec.hint ? `${id}-hint` : undefined;
        const errorId = error ? `${id}-error` : undefined;
        const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
        const shared = {
          id,
          disabled,
          "aria-invalid": error ? true : undefined,
          "aria-describedby": describedBy,
          "aria-required": spec.required || undefined,
        };
        // A start date cannot pass its end, an end cannot precede its start,
        // and a date that already happened cannot be later than this month.
        const min = spec.name === "end_date" ? monthOf(values.start_date) || undefined : undefined;
        const maxCandidates = [
          spec.name === "start_date" ? monthOf(values.end_date) : "",
          spec.notFuture ? now : "",
        ].filter(Boolean);
        const max = maxCandidates.length ? maxCandidates.sort()[0] : undefined;
        const counting = spec.max && value.length > spec.max * 0.8;

        let control: React.ReactNode;
        if (spec.control === "month") {
          control = (
            <MonthPicker
              {...shared}
              value={value}
              min={min}
              max={max}
              emptyMeans={spec.emptyMeans}
              onChange={(v) => { onChange(spec.name, v); onBlur?.(spec.name); }}
            />
          );
        } else if (spec.control === "depth") {
          control = (
            <DepthPicker
              labelledBy={`${id}-label`}
              name={id}
              value={value}
              disabled={disabled}
              describedBy={describedBy}
              onChange={(v) => { onChange(spec.name, v); onBlur?.(spec.name); }}
            />
          );
        } else if (spec.control === "links") {
          const picked = value.split("\n").filter(Boolean);
          control = (
            <div id={id} role="group" aria-labelledby={`${id}-label`} aria-describedby={describedBy} className="flex flex-wrap gap-1.5">
              {(spec.options ?? []).map((o) => {
                const on = picked.includes(o.value);
                return (
                  <button
                    key={o.value}
                    type="button"
                    disabled={disabled}
                    aria-pressed={on}
                    onClick={() => onChange(spec.name, (on ? picked.filter((v) => v !== o.value) : [...picked, o.value]).join("\n"))}
                    className={`min-h-9 rounded-full border px-3 py-1 text-xs transition-colors disabled:opacity-50 ${on ? "border-primary bg-primary text-primary-foreground" : "border-input text-muted-foreground hover:bg-accent"}`}
                  >
                    {on && <span aria-hidden>✓ </span>}
                    {o.label}
                  </button>
                );
              })}
            </div>
          );
        } else if (spec.control === "choice") {
          // Keep a value the entry already has even when it is not one of the
          // offered choices ("Working proficiency" from a resume).
          const options = spec.options ?? [];
          const custom = value && !options.some((o) => o.value === value) ? [{ value, label: value }] : [];
          control = (
            <select {...shared} className={CONTROL} value={value} onChange={(e) => onChange(spec.name, e.target.value)} onBlur={() => onBlur?.(spec.name)}>
              {!spec.required && <option value="">{spec.emptyLabel ?? "Not set"}</option>}
              {spec.required && !value && <option value="" disabled>Choose…</option>}
              {[...custom, ...options].map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          );
        } else if (spec.control === "textarea" || spec.control === "lines") {
          control = (
            <Textarea
              {...shared}
              rows={spec.control === "lines" ? 4 : 3}
              className="min-h-20 text-sm"
              value={value}
              placeholder={spec.placeholder}
              maxLength={spec.max ? spec.max + 200 : undefined}
              onChange={(e) => onChange(spec.name, e.target.value)}
              onBlur={() => onBlur?.(spec.name)}
            />
          );
        } else {
          control = (
            <Input
              {...shared}
              className="h-10 text-sm"
              value={value}
              placeholder={spec.placeholder}
              autoComplete="off"
              onChange={(e) => onChange(spec.name, e.target.value)}
              onBlur={() => onBlur?.(spec.name)}
            />
          );
        }

        return (
          <div key={spec.name} className={`flex min-w-0 flex-col gap-1.5 ${spec.wide || spec.control === "depth" ? "sm:col-span-2" : ""}`}>
            <div className="flex items-baseline justify-between gap-2">
              <label id={`${id}-label`} htmlFor={spec.control === "depth" || spec.control === "links" ? undefined : id} className="text-xs font-semibold text-foreground">
                {spec.label}
                {spec.required ? (
                  <span className="ml-1 text-destructive" aria-hidden>*</span>
                ) : (
                  <span className="ml-1.5 font-normal text-muted-foreground">optional</span>
                )}
              </label>
              {counting && (
                <span className={`text-[11px] tabular-nums ${value.length > (spec.max ?? 0) ? "text-destructive" : "text-muted-foreground"}`}>
                  {value.length}/{spec.max}
                </span>
              )}
            </div>
            {control}
            {error ? (
              <p id={errorId} className="text-xs text-destructive">{error}</p>
            ) : (
              spec.hint && <p id={hintId} className="text-xs text-muted-foreground">{spec.hint}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** A whole form: values, validation, Save/Cancel. Errors appear once a field
 *  has been left, or for every field after a Save attempt; the first invalid
 *  field takes focus so the problem is never off-screen. */
export function EntryForm({
  specs,
  initial,
  submitLabel,
  busyLabel,
  busy,
  error,
  onlyChanged,
  onSubmit,
  onCancel,
}: {
  specs: FieldSpec[];
  initial: Record<string, unknown>;
  submitLabel: string;
  busyLabel: string;
  busy: boolean;
  error?: string | null;
  /** Edit mode: send only what changed, and treat "nothing changed" as Cancel. */
  onlyChanged?: boolean;
  onSubmit: (payload: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [start] = useState<Values>(() => Object.fromEntries(specs.map((s) => [s.name, asFormValue(initial[s.name])])));
  const [values, setValues] = useState<Values>(start);
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [attempted, setAttempted] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const errors = validateEntry(specs, values);
  const shown = attempted ? errors : Object.fromEntries(Object.entries(errors).filter(([n]) => touched.has(n)));
  const invalid = Object.keys(errors).length;
  const dirty = specs.some((s) => values[s.name] !== start[s.name]);

  useEffect(() => {
    // Put the cursor where the typing starts.
    form.current?.querySelector<HTMLElement>("input, textarea, select, button")?.focus();
  }, []);

  function submit() {
    setAttempted(true);
    if (invalid) {
      const first = specs.find((s) => errors[s.name]);
      const el = first && form.current?.querySelector<HTMLElement>(`[id$="-${first.name}"], [name$="-${first.name}"]`);
      el?.focus();
      return;
    }
    const payload: Record<string, unknown> = {};
    for (const spec of specs) {
      if (onlyChanged && values[spec.name] === start[spec.name]) continue;
      payload[spec.name] = fromFormValue(spec, values[spec.name] ?? "");
    }
    if (Object.keys(payload).length === 0) return onCancel();
    onSubmit(payload);
  }

  return (
    <form
      ref={form}
      noValidate
      className="space-y-4"
      onSubmit={(e) => { e.preventDefault(); submit(); }}
    >
      <EntryFields
        specs={specs}
        values={values}
        errors={shown}
        disabled={busy}
        onChange={(name, value) => setValues((v) => ({ ...v, [name]: value }))}
        // A field only starts complaining once it has been changed and left;
        // tabbing past an empty one is not a mistake yet. Save shows the rest.
        onBlur={(name) => setTouched((t) => (t.has(name) || values[name] === start[name] ? t : new Set(t).add(name)))}
      />
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
      <div className="flex flex-wrap items-center gap-2 border-t pt-3">
        <Button type="submit" className="h-10 px-4" disabled={busy || (onlyChanged && !dirty)}>
          {busy ? busyLabel : submitLabel}
        </Button>
        <Button type="button" variant="ghost" className="h-10" disabled={busy} onClick={onCancel}>Cancel</Button>
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {attempted && invalid
            ? `Fix ${invalid} ${invalid === 1 ? "field" : "fields"} to continue.`
            : onlyChanged && !dirty
              ? "No changes yet."
              : ""}
        </span>
      </div>
    </form>
  );
}

/** Month and year, which is what a resume knows. A real picker on every
 *  browser (Safari and Firefox have no native month input). Stores the date
 *  as YYYY-MM-DD; picking the month it already has keeps its day. */
export function MonthPicker({
  id,
  value,
  min,
  max,
  emptyMeans,
  disabled,
  onChange,
  ...aria
}: {
  id?: string;
  value: string;
  min?: string;
  max?: string;
  emptyMeans?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
  "aria-invalid"?: boolean;
  "aria-describedby"?: string;
  "aria-required"?: boolean;
}) {
  const ym = monthOf(value);
  const now = thisMonth();
  const [open, setOpen] = useState(false);
  const [year, setYear] = useState(() => Number((ym || max || now).slice(0, 4)));
  // Years outside min/max hold nothing pickable, so they are not offered.
  const lastYear = Math.max(max ? Number(max.slice(0, 4)) : Number(now.slice(0, 4)) + 8, year);
  const firstYear = Math.min(min ? Number(min.slice(0, 4)) : 1960, year);
  const years = Array.from({ length: lastYear - firstYear + 1 }, (_, i) => lastYear - i);
  const pick = (next: string) => { onChange(dateForMonth(next, value)); setOpen(false); };
  const outOfRange = (m: string) => Boolean((min && m < min) || (max && m > max));

  return (
    <Popover.Root
      open={open}
      onOpenChange={(next) => {
        if (next) setYear(Number((ym || (max && max < now ? max : "") || (min && min > now ? min : "") || now).slice(0, 4)));
        setOpen(next);
      }}
    >
      <Popover.Trigger
        id={id}
        type="button"
        disabled={disabled}
        {...aria}
        className={`${CONTROL} flex items-center gap-2 text-left`}
      >
        <CalendarDays className="size-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className={ym ? "" : "text-muted-foreground"}>{ym ? monthLabel(ym) : emptyMeans ?? "Pick a month"}</span>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={6} align="start" className="z-50">
          <Popover.Popup className="w-72 rounded-xl border bg-popover p-3 text-popover-foreground shadow-xl outline-none">
            <div className="mb-2 flex items-center justify-between gap-2">
              <Button type="button" variant="ghost" size="icon" className="size-9" aria-label="Previous year" disabled={year <= firstYear} onClick={() => setYear((y) => y - 1)}>
                <ChevronLeft className="size-4" />
              </Button>
              <select
                aria-label="Year"
                className="h-9 rounded-md border border-input bg-transparent px-2 text-sm font-semibold dark:bg-input/30"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
              >
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
              <Button type="button" variant="ghost" size="icon" className="size-9" aria-label="Next year" disabled={year >= lastYear} onClick={() => setYear((y) => y + 1)}>
                <ChevronRight className="size-4" />
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-1.5" role="group" aria-label={`Months of ${year}`}>
              {MONTHS.map((name, i) => {
                const m = `${year}-${String(i + 1).padStart(2, "0")}`;
                const selected = m === ym;
                return (
                  <button
                    key={m}
                    type="button"
                    disabled={outOfRange(m)}
                    aria-pressed={selected}
                    aria-label={`${name} ${year}`}
                    onClick={() => pick(m)}
                    className={
                      "h-10 rounded-lg text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-30 " +
                      (selected
                        ? "bg-primary font-semibold text-primary-foreground"
                        : `hover:bg-accent ${m === now ? "ring-1 ring-primary/60" : ""}`)
                    }
                  >
                    {name}
                  </button>
                );
              })}
            </div>
            <div className="mt-3 flex items-center justify-between border-t pt-2">
              <Button type="button" variant="ghost" size="sm" disabled={!value} onClick={() => { onChange(""); setOpen(false); }}>
                {emptyMeans ? `Set to ${emptyMeans}` : "Clear"}
              </Button>
              <Button type="button" variant="ghost" size="sm" disabled={outOfRange(now)} onClick={() => pick(now)}>
                This month
              </Button>
            </div>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Skill depth as five named steps rather than a bare number. Native radios,
 *  so arrow keys move between them. */
function DepthPicker({
  name,
  value,
  labelledBy,
  describedBy,
  disabled,
  onChange,
}: {
  name: string;
  value: string;
  labelledBy: string;
  describedBy?: string;
  disabled?: boolean;
  onChange: (value: string) => void;
}) {
  const chosen = DEPTHS.find((d) => d.value === value);
  return (
    <div>
      <div role="radiogroup" aria-labelledby={labelledBy} aria-describedby={describedBy} className="grid grid-cols-5 overflow-hidden rounded-lg border border-input">
        {DEPTHS.map((d) => (
          <label
            key={d.value}
            className={
              "relative flex cursor-pointer flex-col items-center gap-0.5 border-l border-input px-1 py-1.5 text-center first:border-l-0 has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50 " +
              (d.value === value ? "bg-primary text-primary-foreground" : "hover:bg-accent")
            }
          >
            <input
              type="radio"
              name={name}
              id={`${name}-${d.value}`}
              value={d.value}
              checked={d.value === value}
              disabled={disabled}
              onChange={() => onChange(d.value)}
              className="sr-only"
            />
            <span className="text-sm font-semibold tabular-nums">{d.value}</span>
            <span className="text-[11px] leading-tight">{d.label}</span>
          </label>
        ))}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{chosen ? chosen.hint : "Pick how deeply you have used it."}</p>
    </div>
  );
}
