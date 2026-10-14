import assert from "node:assert/strict";
import { test } from "node:test";
import { holdText } from "../lib/hold-text.ts";

function screen() {
  const shown: string[] = [];
  return { shown, show: (text: string) => shown.push(text) };
}

test("a typed answer's text is shown as it arrives", () => {
  const { shown, show } = screen();
  const text = holdText(show, null);
  text.add("You led ");
  text.add("the migration.");
  assert.deepEqual(shown, ["You led ", "the migration."]);
  assert.equal(text.holding, false);
});

test("a spoken answer's text waits for her voice, then flows", () => {
  const { shown, show } = screen();
  const text = holdText(show, 60_000);
  text.add("You led ");
  text.add("the migration.");
  assert.deepEqual(shown, []);
  text.release();
  text.add(" It took a quarter.");
  text.release(); // her second clip: nothing left to release
  assert.deepEqual(shown, ["You led the migration.", " It took a quarter."]);
});

test("a slow voice never hides the answer", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { shown, show } = screen();
  const text = holdText(show, 4000);
  text.add("You led the migration.");
  t.mock.timers.tick(3999);
  assert.deepEqual(shown, []);
  t.mock.timers.tick(1);
  assert.deepEqual(shown, ["You led the migration."]);
});

test("a failed or abandoned turn shows nothing, even after the timeout", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const { shown, show } = screen();
  const text = holdText(show, 4000);
  text.add("You led the migration.");
  text.discard();
  t.mock.timers.tick(5000);
  text.release();
  assert.deepEqual(shown, []);
});
