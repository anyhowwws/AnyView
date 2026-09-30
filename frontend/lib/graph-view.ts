// The graph's camera: how far in, and where. Pure, so zooming around the
// cursor is tested without a browser.
//
// Layout coordinates are the constellation's own (a 900 × 640 canvas). A
// layout point p is drawn at  C + pan + (p − C) × zoom,  C being the canvas
// centre, in the SVG's viewBox units.

export interface Point { x: number; y: number }
export interface View { zoom: number; pan: Point }

export const WIDTH = 900;
export const HEIGHT = 640;
const C: Point = { x: WIDTH / 2, y: HEIGHT / 2 };

export const MIN_ZOOM = 0.5;
export const MAX_ZOOM = 6;
export const HOME: View = { zoom: 1, pan: { x: 0, y: 0 } };

const clamp = (z: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z));

/** The layout point under a viewBox point. */
export function toLayout(view: View, s: Point): Point {
  return { x: C.x + (s.x - C.x - view.pan.x) / view.zoom, y: C.y + (s.y - C.y - view.pan.y) / view.zoom };
}

/** Zoom by `factor`, keeping whatever is under `s` (viewBox units) under it:
 *  the map grows around the cursor, not around the canvas centre. */
export function zoomAt(view: View, s: Point, factor: number): View {
  const zoom = clamp(view.zoom * factor);
  const p = toLayout(view, s);
  return { zoom, pan: { x: s.x - C.x - (p.x - C.x) * zoom, y: s.y - C.y - (p.y - C.y) * zoom } };
}

/** Put layout point `p` at the canvas centre, at least `minZoom` in. */
export function centreOn(view: View, p: Point, minZoom = 1): View {
  const zoom = clamp(Math.max(view.zoom, minZoom));
  return { zoom, pan: { x: (C.x - p.x) * zoom, y: (C.y - p.y) * zoom } };
}

/** The part of the layout currently on screen. */
export function visibleBounds(view: View): { left: number; top: number; right: number; bottom: number } {
  const a = toLayout(view, { x: 0, y: 0 });
  const b = toLayout(view, { x: WIDTH, y: HEIGHT });
  return { left: a.x, top: a.y, right: b.x, bottom: b.y };
}

/** Wheel ticks to a zoom factor. A trackpad pinch arrives as a wheel event
 *  with ctrlKey set and small deltas, so it gets a steeper curve. */
export function wheelFactor(deltaY: number, pinch: boolean): number {
  return Math.exp(-deltaY * (pinch ? 0.01 : 0.0015));
}
