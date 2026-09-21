"use client";

import { useMemo, useRef, useState } from "react";
import { Network, Search, Minus, Plus, RotateCcw, ArrowUpRight } from "lucide-react";
import { buildBrainGraph, GRAPH_KINDS, KIND_NAMES } from "@/lib/brain-graph";
import type { Brain, EntityKind } from "@/lib/types";
import { Button } from "@/components/ui/button";

export function BrainGraph({ brain, onBrowse }: { brain: Brain; onBrowse: () => void }) {
  const { nodes, edges } = useMemo(() => buildBrainGraph(brain), [brain]);
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState<EntityKind | "all">("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const viewport = useRef<HTMLDivElement>(null);
  const selected = nodes.find((n) => n.id === selectedId);
  const matches = nodes.filter((n) => (kind === "all" || n.kind === kind) && `${n.title} ${n.label} ${n.detail}`.toLowerCase().includes(query.toLowerCase()));
  const matchIds = new Set(matches.map((n) => n.id));
  const neighbors = new Set(edges.flatMap((e) => e.from === selectedId ? [e.to] : e.to === selectedId ? [e.from] : []));
  const groups = GRAPH_KINDS.filter((k) => nodes.some((n) => n.kind === k));
  const height = Math.max(400, ...groups.map((k) => nodes.filter((n) => n.kind === k).length * 110 + 90));
  const width = Math.max(780, groups.length * 240 + 40);
  const positions = new Map(nodes.map((n) => {
    const peers = nodes.filter((p) => p.kind === n.kind);
    return [n.id, { x: 30 + groups.indexOf(n.kind) * 240, y: 65 + (height - 90 - peers.length * 110) / 2 + peers.indexOf(n) * 110 }];
  }));
  function inspect(id: string) {
    setSelectedId(id);
    const position = positions.get(id);
    if (position) viewport.current?.scrollTo({ left: Math.max(0, position.x * zoom - 80), top: Math.max(0, position.y * zoom - 100) });
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
    <section className="brain-map" aria-label="Digital Garden relationship map">
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
          <div ref={viewport} className="graph-viewport" tabIndex={0} aria-label="Scrollable graph. Use arrow keys to scroll, or select an entry below.">
            <div style={{ width: width * zoom, height: height * zoom }}>
              <div className="graph-world" style={{ width, height, transform: `scale(${zoom})` }}>
                <svg width={width} height={height} aria-hidden className="graph-edges">
                  {edges.map((e) => {
                    const a = positions.get(e.from)!; const b = positions.get(e.to)!;
                    const active = e.from === selectedId || e.to === selectedId;
                    return <path key={`${e.from}-${e.to}`} d={`M ${a.x + 186} ${a.y + 36} C ${a.x + 218} ${a.y + 36}, ${b.x - 35} ${b.y + 36}, ${b.x} ${b.y + 36}`} className={active ? "graph-edge active" : "graph-edge"} />;
                  })}
                </svg>
                {groups.map((k, i) => <div key={k} className="graph-column-label" style={{ left: 30 + i * 240 }}>{KIND_NAMES[k]} <span>{nodes.filter((n) => n.kind === k).length}</span></div>)}
                {nodes.map((n) => {
                  const pos = positions.get(n.id)!;
                  const muted = !matchIds.has(n.id) || (selected && n.id !== selectedId && !neighbors.has(n.id));
                  return <button key={n.id} type="button" className={`graph-node ${n.id === selectedId ? "selected" : ""} ${muted ? "muted-node" : ""}`} style={{ left: pos.x, top: pos.y }} aria-pressed={n.id === selectedId} aria-label={`${n.label}: ${n.title}, ${n.kind}`} onClick={() => setSelectedId(n.id === selectedId ? null : n.id)}>
                    <span className="node-kind">{n.label} <span>{n.kind}</span></span><span className="node-title">{n.title}</span>
                  </button>;
                })}
              </div>
            </div>
          </div>
          <div className="graph-footer">
            <p>{edges.length} confirmed connections <span className="hidden sm:inline">· Select an entry to explore</span></p>
            <div className="flex items-center">
              <Button variant="ghost" size="icon" aria-label="Zoom out" disabled={zoom <= 0.6} onClick={() => setZoom((z) => Math.max(0.6, z - 0.2))}><Minus size={16} /></Button>
              <span className="w-12 text-center tabular-nums">{Math.round(zoom * 100)}%</span>
              <Button variant="ghost" size="icon" aria-label="Zoom in" disabled={zoom >= 1.8} onClick={() => setZoom((z) => Math.min(1.8, z + 0.2))}><Plus size={16} /></Button>
              <Button variant="ghost" size="icon" aria-label="Reset graph view" onClick={() => { setZoom(1); setSelectedId(null); setQuery(""); setKind("all"); viewport.current?.scrollTo(0, 0); }}><RotateCcw size={15} /></Button>
            </div>
          </div>
        </div>
        <aside className="graph-inspector" aria-label="Entry details">
          {selected ? <>
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
