import assert from "node:assert/strict";
import { test } from "node:test";
import { HOME, MAX_ZOOM, MIN_ZOOM, centreOn, toLayout, visibleBounds, wheelFactor, zoomAt } from "../lib/graph-view.ts";
import { visibleConstellationLabels, type ConstellationPoint } from "../lib/constellation.ts";
import type { BrainNode } from "../lib/brain-graph.ts";

const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-9, `${a} ≈ ${b}`);

test("zooming keeps the point under the cursor where it is", () => {
  const cursor = { x: 700, y: 120 };
  const before = toLayout(HOME, cursor);
  const view = zoomAt(HOME, cursor, 2.5);
  const after = toLayout(view, cursor);
  close(after.x, before.x);
  close(after.y, before.y);
  assert.equal(view.zoom, 2.5);
});

test("zoom is clamped, and centring puts a point in the middle", () => {
  assert.equal(zoomAt(HOME, { x: 0, y: 0 }, 100).zoom, MAX_ZOOM);
  assert.equal(zoomAt(HOME, { x: 0, y: 0 }, 0.001).zoom, MIN_ZOOM);
  const view = centreOn(HOME, { x: 100, y: 500 }, 2);
  const middle = toLayout(view, { x: 450, y: 320 });
  close(middle.x, 100);
  close(middle.y, 500);
  assert.equal(view.zoom, 2);
});

test("the visible part of the layout shrinks as you zoom in", () => {
  const home = visibleBounds(HOME);
  assert.deepEqual(home, { left: 0, top: 0, right: 900, bottom: 640 });
  const inside = visibleBounds(zoomAt(HOME, { x: 450, y: 320 }, 2));
  assert.deepEqual(inside, { left: 225, top: 160, right: 675, bottom: 480 });
  assert.ok(wheelFactor(-100, false) > 1 && wheelFactor(100, false) < 1);
  assert.ok(wheelFactor(-10, true) > wheelFactor(-10, false));
});

test("zooming in makes room for more labels, and off-screen nodes take none", () => {
  const source = { raw_dump_id: "d", event_id: 1 };
  // Twenty nodes packed 12 units apart: far too close for labels at 100%.
  const nodes: BrainNode[] = Array.from({ length: 20 }, (_, i) => ({ id: `n${i}`, kind: "skill", label: `K${i}`, title: `Skill number ${i}`, detail: "", source }));
  const positions = new Map<string, ConstellationPoint>(nodes.map((n, i) => [n.id, { id: n.id, x: 400 + (i % 5) * 12, y: 300 + Math.floor(i / 5) * 12, degree: 0 }]));
  const home = visibleConstellationLabels(nodes, positions).size;
  const zoom = 6;
  const view = zoomAt(HOME, { x: 424, y: 318 }, zoom);
  const near = visibleConstellationLabels(nodes, positions, { zoom: view.zoom, bounds: visibleBounds(view) }).size;
  assert.ok(near > home, `${near} labels at ${zoom}x vs ${home} at 1x`);
  const away = visibleConstellationLabels(nodes, positions, { zoom: 2, bounds: { left: 0, top: 0, right: 100, bottom: 100 } });
  assert.equal(away.size, 0);
});
