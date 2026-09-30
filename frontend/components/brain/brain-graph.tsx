"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Network, Search, Minus, Plus, RotateCcw, ArrowUpRight } from "lucide-react";
import { buildBrainGraph, GRAPH_KINDS, KIND_COLORS, KIND_NAMES } from "@/lib/brain-graph";
import type { Brain, EntityKind } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { layout, nodeRadius, visibleConstellationLabels, type ConstellationPoint, type Lens, type Territory } from "@/lib/constellation";
import { HOME, HEIGHT, MAX_ZOOM, MIN_ZOOM, WIDTH, centreOn, visibleBounds, wheelFactor, zoomAt, type Point, type View } from "@/lib/graph-view";

const LENSES: { value: Lens; label: string; blurb: string }[] = [
  { value: "constellation", label: "Constellation", blurb: "Connections alone decide where entries sit. Tightly linked work pulls together." },
  { value: "role", label: "By role", blurb: "Each role anchors its own territory. A skill used in two roles settles between them, so the overlap is what you carry from job to job." },
  { value: "kind", label: "By kind", blurb: "One cluster per entry type. The lines between clusters show which skills have projects behind them, and which stand alone." },
];

function territoryName(t: Territory): string {
  const name = t.label || KIND_NAMES[t.kind];
  return name.length > 28 ? name.slice(0, 27) + "…" : name;
}

const COLORS = KIND_COLORS;
// A press that moves less than this (screen px) is a click, not a drag.
const CLICK_SLOP = 4;

/** What the pointer is doing on the canvas. One gesture at a time. */
type Gesture =
  | { mode: "pan"; start: Point; pan: Point; moved: boolean }
  | { mode: "node"; id: string; start: Point; from: Point; moved: boolean }
  | { mode: "pinch"; distance: number };

export function BrainGraph({ brain, onBrowse }: { brain: Brain; onBrowse: () => void }) {
  const { nodes, edges } = useMemo(() => buildBrainGraph(brain), [brain]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<EntityKind | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [view, setView] = useState<View>(HOME);
  const [labels, setLabels] = useState(true);
  const [lens, setLens] = useState<Lens>("constellation");
  // Where the user has dragged nodes to, in layout units. Cleared per lens.
  const [moved, setMoved] = useState<Record<string, Point>>({});
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const reduceMotion = useReducedMotion();
  const move = { duration: reduceMotion ? 0 : 0.7, ease: [0.22, 1, 0.36, 1] as const };
  const still = { duration: 0 };
  const svg = useRef<SVGSVGElement>(null);
  const gesture = useRef<Gesture | null>(null);
  const pointers = useRef(new Map<number, Point>());

  const { positions: laidOut, territories } = useMemo(() => layout(nodes, edges, lens), [nodes, edges, lens]);
  const positions = useMemo(() => {
    const out = new Map<string, ConstellationPoint>();
    laidOut.forEach((p, id) => out.set(id, moved[id] ? { ...p, ...moved[id] } : p));
    return out;
  }, [laidOut, moved]);
  const visibleLabels = useMemo(
    () => visibleConstellationLabels(nodes, positions, { zoom: view.zoom, bounds: visibleBounds(view) }),
    [nodes, positions, view],
  );
  const selected = nodes.find((n) => n.id === selectedId);
  const focusId = hoveredId ?? selectedId;
  const matches = nodes.filter((n) => (kind === "all" || n.kind === kind) && `${n.title} ${n.label} ${n.detail}`.toLowerCase().includes(query.toLowerCase()));
  const matchIds = new Set(matches.map((n) => n.id));
  const neighborsOf = (id: string | null) => new Set(edges.flatMap((e) => e.from === id ? [e.to] : e.to === id ? [e.from] : []));
  const neighbors = neighborsOf(selectedId);
  const lit = neighborsOf(focusId);

  /** A pointer event's position in the SVG's viewBox units. */
  function toViewBox(clientX: number, clientY: number): Point {
    const rect = svg.current!.getBoundingClientRect();
    return { x: (clientX - rect.left) * (WIDTH / rect.width), y: (clientY - rect.top) * (HEIGHT / rect.height) };
  }
  const pxToViewBox = () => WIDTH / svg.current!.getBoundingClientRect().width;

  // Wheel and trackpad pinch zoom around the cursor. Attached by hand because
  // React's onWheel is passive and cannot stop the page scrolling instead.
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const at = toViewBox(e.clientX, e.clientY);
      setView((v) => zoomAt(v, at, wheelFactor(e.deltaY, e.ctrlKey)));
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [nodes.length > 0]); // eslint-disable-line react-hooks/exhaustive-deps

  function inspect(id: string) {
    setSelectedId(id);
    const p = positions.get(id);
    if (p) setView((v) => centreOn(v, p, 1.6));
  }

  function switchLens(next: Lens) {
    setLens(next);
    setMoved({});
  }

  function onPointerDown(e: React.PointerEvent<SVGSVGElement>) {
    try {
      e.currentTarget.setPointerCapture(e.pointerId); // keep the drag when the pointer leaves the canvas
    } catch {
      // The pointer was already gone (released during the press); the gesture still works in-canvas.
    }
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      gesture.current = { mode: "pinch", distance: Math.hypot(a.x - b.x, a.y - b.y) };
      setDraggingId(null);
      return;
    }
    const nodeId = (e.target as Element).closest<SVGElement>("[data-node-id]")?.dataset.nodeId;
    const start = { x: e.clientX, y: e.clientY };
    gesture.current = nodeId
      ? { mode: "node", id: nodeId, start, from: positions.get(nodeId)!, moved: false }
      : { mode: "pan", start, pan: view.pan, moved: false };
  }

  function onPointerMove(e: React.PointerEvent<SVGSVGElement>) {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const g = gesture.current;
    if (!g) return;
    if (g.mode === "pinch") {
      const [a, b] = [...pointers.current.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      const at = toViewBox((a.x + b.x) / 2, (a.y + b.y) / 2);
      setView((v) => zoomAt(v, at, distance / g.distance));
      g.distance = distance;
      return;
    }
    const dx = e.clientX - g.start.x, dy = e.clientY - g.start.y;
    if (!g.moved && Math.hypot(dx, dy) < CLICK_SLOP) return;
    g.moved = true;
    const k = pxToViewBox();
    if (g.mode === "pan") {
      setView((v) => ({ ...v, pan: { x: g.pan.x + dx * k, y: g.pan.y + dy * k } }));
    } else {
      setDraggingId(g.id);
      setMoved((m) => ({ ...m, [g.id]: { x: g.from.x + (dx * k) / view.zoom, y: g.from.y + (dy * k) / view.zoom } }));
    }
  }

  function onPointerUp(e: React.PointerEvent<SVGSVGElement>) {
    pointers.current.delete(e.pointerId);
    const g = gesture.current;
    if (g?.mode === "node" && !g.moved) setSelectedId((s) => (s === g.id ? null : g.id));
    if (g?.mode === "pan" && !g.moved && e.type === "pointerup") setSelectedId(null);
    gesture.current = null;
    setDraggingId(null);
  }

  if (!nodes.length) return (
    <div className="graph-empty">
      <Network size={44} strokeWidth={1.2} aria-hidden />
      <h3>Your experience has connections.</h3>
      <p>Add a project, a memorable moment, or your resume above. Confirm the suggested entries to start seeing your map take shape.</p>
      <a href="#dump" className="text-primary underline underline-offset-4">Capture your first memory</a>
    </div>
  );

  // Node dots and every label keep their size on screen: the map spreads out
  // under them as you zoom, which is what makes room for more names.
  const glyph = `scale(${1 / view.zoom})`;
  const zoomTo = (factor: number) => setView((v) => zoomAt(v, { x: WIDTH / 2, y: HEIGHT / 2 }, factor));

  return (
    <section className="brain-map constellation" aria-label="Digital Garden relationship map">
      <div className="constellation-heading"><div><span>YOUR KNOWLEDGE, CONNECTED</span><h3>Experience constellation</h3></div><span className="constellation-status">● {nodes.length} confirmed entries</span></div>
      <div className="graph-toolbar">
        <label className="graph-search"><Search size={17} aria-hidden /><span className="sr-only">Search brain graph</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a story, skill, or project…" /></label>
        <label className="sr-only" htmlFor="graph-type">Entry type</label>
        <select id="graph-type" value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} className="graph-filter">
          <option value="all">All entry types</option>
          {GRAPH_KINDS.map((k) => <option key={k} value={k}>{KIND_NAMES[k]}</option>)}
        </select>
        <div className="graph-lenses" role="group" aria-label="Arrange the map">
          {LENSES.map((l) => (
            <button key={l.value} type="button" aria-pressed={lens === l.value} onClick={() => switchLens(l.value)}>{l.label}</button>
          ))}
        </div>
        <span className="text-xs text-muted-foreground" role="status">{matches.length ? `${matches.length} of ${nodes.length} entries` : "No matches. Try another search."}</span>
      </div>
      <div className="graph-layout">
        <div className="graph-stage">
          <svg ref={svg} className="constellation-canvas" viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            aria-label="Knowledge constellation. Scroll or pinch to zoom, drag to pan, drag an entry to move it. Entries are also listed under Find an entry."
            onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
            onDoubleClick={(e) => { if (!(e.target as Element).closest("[data-node-id]")) setView((v) => zoomAt(v, toViewBox(e.clientX, e.clientY), 1.8)); }}>
            <g className="constellation-rings" aria-hidden="true">{[100, 195, 285].map((r) => <circle key={r} cx="450" cy="320" r={r} />)}<path d="M 450 20 V 620 M 50 320 H 850" /></g>
            <g transform={`translate(${WIDTH / 2 + view.pan.x} ${HEIGHT / 2 + view.pan.y}) scale(${view.zoom}) translate(${-WIDTH / 2} ${-HEIGHT / 2})`}>
              <g className="constellation-territories" aria-hidden="true">
                {territories.map((t) => (
                  <motion.g key={`${lens}-${t.id}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={move}>
                    <circle cx={t.x} cy={t.y} r={t.r} fill={COLORS[t.kind]} stroke={COLORS[t.kind]} vectorEffect="non-scaling-stroke" />
                    <text x={t.x} y={t.y - t.r + 16 / view.zoom} textAnchor="middle" style={{ fontSize: 10 / view.zoom }}>{territoryName(t)}</text>
                  </motion.g>
                ))}
              </g>
              {edges.map((e) => {
                const a = positions.get(e.from)!, b = positions.get(e.to)!;
                const active = e.from === focusId || e.to === focusId;
                const dragging = e.from === draggingId || e.to === draggingId;
                return <motion.line key={`${e.from}-${e.to}`} initial={false} animate={{ x1: a.x, y1: a.y, x2: b.x, y2: b.y }} transition={dragging ? still : move}
                  className={`constellation-edge ${active ? "lit" : ""}`} vectorEffect="non-scaling-stroke" opacity={focusId && !active ? .12 : 1} />;
              })}
              {nodes.map((n) => {
                const p = positions.get(n.id)!;
                const active = n.id === selectedId;
                const hovered = n.id === hoveredId;
                const muted = !matchIds.has(n.id) || Boolean(focusId && n.id !== focusId && !lit.has(n.id));
                const radius = nodeRadius(p.degree);
                const named = active || hovered || (labels && visibleLabels.has(n.id));
                const title = active || hovered || n.title.length <= 25 ? n.title : n.title.slice(0, 24) + "…";
                return <motion.g key={n.id} data-node-id={n.id} role="button" tabIndex={0} aria-pressed={active} aria-label={`${n.label}: ${n.title}, ${n.kind}`}
                  className={`constellation-node ${active ? "selected" : ""} ${hovered ? "hovered" : ""}`} opacity={muted ? .35 : 1}
                  initial={false} animate={{ x: p.x, y: p.y }} transition={n.id === draggingId ? still : move}
                  onPointerEnter={() => setHoveredId(n.id)} onPointerLeave={() => setHoveredId((h) => (h === n.id ? null : h))}
                  onFocus={() => setHoveredId(n.id)} onBlur={() => setHoveredId(null)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedId(active ? null : n.id); } }}>
                  <g transform={glyph}>
                    <circle r={radius + 12} fill={COLORS[n.kind]} opacity=".07" />
                    <circle className="node-orbit" r={radius + 6} fill="none" stroke={COLORS[n.kind]} opacity={active || hovered ? 1 : .3} />
                    <circle r={radius} fill={COLORS[n.kind]} />
                    <circle r="2" fill="#fff" />
                    {named && <text y={radius + 25} textAnchor="middle">{title}</text>}
                  </g>
                </motion.g>;
              })}
            </g>
          </svg>
          <div className="constellation-legend">{GRAPH_KINDS.filter((k) => nodes.some((n) => n.kind === k)).map((k) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(kind === k ? "all" : k)}><i style={{ background: COLORS[k] }} />{KIND_NAMES[k]}</button>)}</div>
          <div className="graph-footer">
            <p>{edges.length} confirmed connections <span className="hidden sm:inline">. Scroll to zoom, drag to explore, hover to read.</span></p>
            <div className="flex items-center">
              <Button variant="ghost" size="icon" aria-label="Zoom out" disabled={view.zoom <= MIN_ZOOM} onClick={() => zoomTo(1 / 1.3)}><Minus size={16} /></Button>
              <span className="w-12 text-center tabular-nums">{Math.round(view.zoom * 100)}%</span>
              <Button variant="ghost" size="icon" aria-label="Zoom in" disabled={view.zoom >= MAX_ZOOM} onClick={() => zoomTo(1.3)}><Plus size={16} /></Button>
              <Button variant="ghost" size="icon" aria-label="Reset graph view" onClick={() => { setView(HOME); setMoved({}); setSelectedId(null); setQuery(""); setKind("all"); }}><RotateCcw size={15} /></Button>
              <button className="constellation-label-toggle" aria-pressed={labels} onClick={() => setLabels(!labels)}>Labels</button>
            </div>
          </div>
        </div>
        <aside className="graph-inspector" aria-label="Entry details">
          {selected ? <>
            <Button variant="ghost" onClick={() => setSelectedId(null)}>Clear selection</Button>
            <p className="eyebrow">{selected.kind} · {selected.label}</p>
            <h3>{selected.title}</h3>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">{selected.detail || "No additional details yet."}</p>
            <h4 className="mt-6 text-xs font-semibold">Connected entries · {neighbors.size}</h4>
            {nodes.filter((n) => neighbors.has(n.id)).map((n) => <button className="connection-link" key={n.id} onClick={() => inspect(n.id)}><span>{n.label} · {n.title}</span><ArrowUpRight size={14} aria-hidden /></button>)}
            {!neighbors.size && <p className="text-sm text-muted-foreground">No confirmed links to other entries.</p>}
            <Button variant="outline" className="mt-5" onClick={onBrowse}>Browse and edit entries</Button>
          </> : <>
            <Network size={25} className="text-primary" aria-hidden />
            <h3>Follow the connections.</h3>
            <p className="text-sm leading-relaxed text-muted-foreground">Scroll or pinch to zoom in, and names appear as there is room for them. Drag the map to explore, drag an entry to pull it apart from its cluster, and hover to read any name.</p>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground"><span className="font-medium text-foreground">{LENSES.find((l) => l.value === lens)!.label}.</span> {LENSES.find((l) => l.value === lens)!.blurb}</p>
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">Every line is a relationship in your confirmed Digital Garden. Entries without a recorded link stand on their own.</p>
          </>}
          <details className="mt-6 border-t pt-4">
            <summary className="cursor-pointer text-sm font-medium">Find an entry ({matches.length})</summary>
            <div className="mt-2 max-h-52 overflow-y-auto">
              {matches.map((n) => <button key={n.id} className="connection-link" onClick={() => inspect(n.id)}>{n.label} · {n.title}</button>)}
              {!matches.length && <p className="py-3 text-sm text-muted-foreground">No matches. Try another search or entry type.</p>}
            </div>
          </details>
        </aside>
      </div>
    </section>
  );
}
