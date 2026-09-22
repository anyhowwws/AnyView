import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../app/theme.css', import.meta.url), 'utf8');
const color = (name: string) => {
  const value = css.match(new RegExp(`--${name}: (#[0-9a-f]{6});`))?.[1];
  assert.ok(value, `Missing ${name} token`);
  return value;
};
function luminance(hex: string) {
  const rgb = hex.slice(1).match(/../g)!.map((v) => parseInt(v, 16) / 255)
    .map((v) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
}
test('Garden text and control colors meet contrast targets', () => {
  for (const [fg, bg, minimum] of [
    ['foreground', 'background', 4.5], ['card-foreground', 'card', 4.5],
    ['muted-foreground', 'card', 4.5], ['popover-foreground', 'popover', 4.5],
    ['primary-foreground', 'primary', 4.5], ['destructive', 'card', 4.5],
    ['input', 'background', 3], ['ring', 'card', 3],
  ] as const) {
    const a = luminance(color(fg)), b = luminance(color(bg));
    const ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    assert.ok(ratio >= minimum, `${fg} on ${bg}: ${ratio.toFixed(2)}:1`);
  }
});
