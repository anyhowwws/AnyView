"use client";

import { useMemo, useRef, useState } from "react";
import { Network, Search, Minus, Plus, RotateCcw, ArrowUpRight } from "lucide-react";
import { buildBrainGraph, GRAPH_KINDS, KIND_NAMES } from "@/lib/brain-graph";
import type { Brain, EntityKind } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { constellation, visibleConstellationLabels } from "@/lib/constellation";

const COLORS: Record<EntityKind, string> = { role: "#ffbe72", project: "#75e4cf", story: "#a5a3ff", skill: "#76c8ff", achievement: "#f1d78a", education: "#ed9dbf", language: "#b7da87" };

export function BrainGraph({ brain, onBrowse }: { brain: Brain; onBrowse: () => void }) {
  const { nodes, edges } = useMemo(() => buildBrainGraph(brain), [brain]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<EntityKind | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [labels, setLabels] = useState(true);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const positions = useMemo(() => constellation(nodes, edges), [nodes, edges]);
  const visibleLabels = useMemo(() => visibleConstellationLabels(nodes, positions), [nodes, positions]);
  const selected = nodes.find((n) => n.id === selectedId);
  const matches = nodes.filter((n) => (kind === "all" || n.kind === kind) && `${n.title} ${n.label} ${n.detail}`.toLowerCase().includes(query.toLowerCase()));
  const matchIds = new Set(matches.map((n) => n.id));
  const neighbors = new Set(edges.flatMap((e) => e.from === selectedId ? [e.to] : e.to === selectedId ? [e.from] : []));
  function inspect(id: string) {
    setSelectedId(id);
    const position = positions.get(id);
    if (position) setPan({ x: (450 - position.x) * zoom, y: (320 - position.y) * zoom });
  }

  if (!nodes.length) return (
    <div className="graph-empty">
      <Network size={44} strokeWidth={1.2} aria-hidden />
      <h3>Your experience has connections.</h3>
      <p>Add a project, a memorable moment, or your resume above. Confirm the suggested entries to start seeing your map take shape.</p>
      <a href="#dump" className="text-primary underline underline-offset-4">Capture your first memory</a>
    </div>
  );

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
        <span className="text-xs text-muted-foreground" role="status">{matches.length ? `${matches.length} of ${nodes.length} entries` : "No matches. Try another search."}</span>
      </div>
      <div className="graph-layout">
        <div className="graph-stage">
          <svg className="constellation-canvas" viewBox="0 0 900 640" aria-label="Knowledge constellation. Drag the background to pan; use the zoom controls below."
            onPointerDown={(e) => { if ((e.target as Element).closest("[role=button]")) return; e.currentTarget.setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y }; }}
            onPointerMove={(e) => { if (!drag.current) return; const scale = 900 / e.currentTarget.getBoundingClientRect().width; setPan({ x: drag.current.px + (e.clientX - drag.current.x) * scale, y: drag.current.py + (e.clientY - drag.current.y) * scale }); }}
            onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
            <g className="constellation-rings" aria-hidden="true">{[100, 195, 285].map((r) => <circle key={r} cx="450" cy="320" r={r} />)}<path d="M 450 20 V 620 M 50 320 H 850" /></g>
            <g transform={`translate(${450 + pan.x} ${320 + pan.y}) scale(${zoom}) translate(-450 -320)`}>
              {edges.map((e) => {
                const a = positions.get(e.from)!, b = positions.get(e.to)!;
                const active = e.from === selectedId || e.to === selectedId;
                return <line key={`${e.from}-${e.to}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={`constellation-edge ${active ? "lit" : ""}`} opacity={selected && !active ? .12 : 1} />;
              })}
              {nodes.map((n) => {
                const p = positions.get(n.id)!;
                const active = n.id === selectedId;
                const muted = !matchIds.has(n.id) || Boolean(selected && !active && !neighbors.has(n.id));
                const radius = 5 + Math.min(p.degree, 9) * 1.4;
                return <g key={n.id} role="button" tabIndex={0} aria-pressed={active} aria-label={`${n.label}: ${n.title}, ${n.kind}`}
                  className={`constellation-node ${active ? "selected" : ""}`} opacity={muted ? .4 : 1} transform={`translate(${p.x} ${p.y})`}
                  onClick={() => setSelectedId(active ? null : n.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setSelectedId(active ? null : n.id); } }}>
                  <title>{n.title}</title>
                  <circle r={radius + 12} fill={COLORS[n.kind]} opacity=".07" />
                  <circle className="node-orbit" r={radius + 6} fill="none" stroke={COLORS[n.kind]} opacity={active ? 1 : .3} />
                  <circle r={radius} fill={COLORS[n.kind]} />
                  <circle r="2" fill="#fff" />
                  {(active || (labels && visibleLabels.has(n.id))) && <text y={radius + 25} textAnchor="middle">{n.title.length > 25 ? n.title.slice(0, 24) + "…" : n.title}</text>}
                </g>;
              })}
            </g>
          </svg>
          <div className="constellation-legend">{GRAPH_KINDS.filter((k) => nodes.some((n) => n.kind === k)).map((k) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(kind === k ? "all" : k)}><i style={{ background: COLORS[k] }} />{KIND_NAMES[k]}</button>)}</div>
          <div className="graph-footer">
            <p>{edges.length} confirmed connections <span className="hidden sm:inline">· Select an entry to explore</span></p>
            <div className="flex items-center">
              <Button variant="ghost" size="icon" aria-label="Zoom out" disabled={zoom <= 0.6} onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}><Minus size={16} /></Button>
              <span className="w-12 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
              <Button variant="ghost" size="icon" aria-label="Zoom in" disabled={zoom >= 1.8} onClick={() => setZoom((z) => Math.min(1.8, z + 0.2))}><Plus size={16} /></Button>
              <Button variant="ghost" size="icon" aria-label="Reset graph view" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); setSelectedId(null); setQuery(""); setKind("all"); }}><RotateCcw size={15} /></Button>
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
            <p className="text-sm leading-relaxed text-muted-foreground">See how your roles connect to projects, the stories behind them, and the skills they demonstrate.</p>
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">Every line is a relationship in your confirmed Digital Garden. Certifications, education, and languages without a recorded link stand on their own.</p>
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
