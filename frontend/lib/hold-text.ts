/** A spoken Discover answer's text, held back until Donna starts speaking
 *  (ADR 0033). The text streams in a second or two before her first clip is
 *  synthesised; shown at once, it would be half read by the time she talks
 *  over it. Kept free of React so the rules can be tested on their own. */

export interface HeldText {
  /** A chunk from the stream: kept back while holding, shown otherwise. */
  add(chunk: string): void;
  /** Show everything kept back, and every chunk after it. Safe to call twice. */
  release(): void;
  /** Drop what is kept back without showing it: the turn failed or was abandoned. */
  discard(): void;
  readonly holding: boolean;
}

/** `holdMs` null passes text straight through (a typed question). Otherwise
 *  text is held until `release()` — her first clip, her voice failing, Stop,
 *  the end of the stream — or until `holdMs` passes, so a slow voice never
 *  hides the answer. */
export function holdText(show: (text: string) => void, holdMs: number | null): HeldText {
  let held: string | null = holdMs === null ? null : "";
  const timer = holdMs === null ? undefined : setTimeout(() => release(), holdMs);

  function discard() {
    held = null;
    clearTimeout(timer);
  }

  function release() {
    if (held === null) return;
    const text = held;
    discard();
    if (text) show(text);
  }

  return {
    add(chunk) {
      if (held !== null) held += chunk;
      else show(chunk);
    },
    release,
    discard,
    get holding() {
      return held !== null;
    },
  };
}
