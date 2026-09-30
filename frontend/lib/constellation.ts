import type { BrainNode, BrainEdge } from "./brain-graph";
import type { EntityKind } from "./types";

export type ConstellationPoint = { id: string; x: number; y: number; degree: number };

/** How the constellation is arranged. Every lens draws the same confirmed
 *  edges; only where the nodes settle changes.
 *  - constellation: connections alone decide.
 *  - role: each role is an anchor; everything settles near the roles it is
 *    evidenced in, so a skill used in two jobs sits between them.
 *  - kind: one cluster per entry type; the lines between clusters are the story. */
export type Lens = "constellation" | "role" | "kind";

/** A soft region drawn behind a cluster: a role's territory (labelled with the
 *  role's name), or a kind's group (label empty: the UI names the kind). */
export type Territory = { id: string; label: string; kind: EntityKind; x: number; y: number; r: number };

/** Bounded, deterministic spring layout. Only confirmed edges exert attraction. */
export function constellation(nodes: BrainNode[], edges: BrainEdge[]) {
  return layout(nodes, edges, "constellation").positions;
}

/** The roles each entry belongs to, through confirmed links only: a project
 *  through its role, a story or feedback through its role or its project's
 *  role, a skill through the projects that evidence it and the roles it was
 *  used in. An entry with no path to a role belongs to none. */
export function homeRoles(nodes: BrainNode[], edges: BrainEdge[]): Map<string, string[]> {
  const kindOf = new Map(nodes.map((n) => [n.id, n.kind]));
  const roleOfProject = new Map<string, string>();
  edges.forEach((e) => { if (kindOf.get(e.from) === "role" && kindOf.get(e.to) === "project") roleOfProject.set(e.to, e.from); });
  const homes = new Map<string, string[]>();
  const add = (id: string, role: string | undefined) => {
    if (!role) return;
    const list = homes.get(id) ?? [];
    if (!list.includes(role)) homes.set(id, [...list, role]);
  };
  nodes.forEach((n) => { if (n.kind === "role") add(n.id, n.id); });
  edges.forEach((e) => {
    if (kindOf.get(e.to) === "role") return;
    const from = kindOf.get(e.from);
    if (from === "role") add(e.to, e.from);
    else if (from === "project") add(e.to, roleOfProject.get(e.from));
  });
  return homes;
}

const RING = 230; // where lens anchors sit, in layout units around the origin

export function layout(nodes: BrainNode[], edges: BrainEdge[], lens: Lens) {
  const points = nodes.map((n, i) => ({ id: n.id, x: Math.cos(i * 2.39996) * (50 + Math.sqrt(i) * 35), y: Math.sin(i * 2.39996) * (50 + Math.sqrt(i) * 35), degree: 0 }));
  const byId = new Map(points.map((p) => [p.id, p]));
  const links = edges.map((e) => [byId.get(e.from)!, byId.get(e.to)!]).filter(([a, b]) => a && b);
  links.forEach(([a, b]) => { a.degree++; b.degree++; });

  // Where each lens wants a node to be. Roles (role lens) are pinned to their
  // anchor; everything else is pulled toward the mean of its anchors.
  const roles = nodes.filter((n) => n.kind === "role");
  const kinds = [...new Set(nodes.map((n) => n.kind))];
  const around = (i: number, count: number) => count === 1
    ? { x: 0, y: 0 }
    // Start on the left, so two roles sit side by side on the wide canvas.
    : { x: Math.cos((i / count) * 2 * Math.PI + Math.PI) * RING, y: Math.sin((i / count) * 2 * Math.PI + Math.PI) * RING };
  const roleAnchor = new Map(roles.map((r, i) => [r.id, around(i, roles.length)]));
  const kindAnchor = new Map(kinds.map((k, i) => [k, around(i, kinds.length)]));
  const homes = homeRoles(nodes, edges);
  const target = new Map<string, { x: number; y: number } | null>();
  nodes.forEach((n) => {
    if (lens === "kind") return target.set(n.id, kindAnchor.get(n.kind)!);
    if (lens === "role") {
      const anchors = (homes.get(n.id) ?? []).map((r) => roleAnchor.get(r)!).filter(Boolean);
      if (!anchors.length) return target.set(n.id, null);
      return target.set(n.id, { x: anchors.reduce((s, a) => s + a.x, 0) / anchors.length, y: anchors.reduce((s, a) => s + a.y, 0) / anchors.length });
    }
    target.set(n.id, null);
  });
  const pull = lens === "kind" ? 0.07 : 0.05;
  const springs = lens === "kind" ? 0.004 : 0.025; // in the kind lens, clusters matter more than links

  for (let step = 0; step < 160; step++) {
    const forces = points.map((p) => ({ x: -p.x * .008, y: -p.y * .008 }));
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dx = points[i].x - points[j].x, dy = points[i].y - points[j].y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const force = Math.min(12, 2200 / (distance * distance));
        forces[i].x += dx / distance * force; forces[i].y += dy / distance * force;
        forces[j].x -= dx / distance * force; forces[j].y -= dy / distance * force;
      }
    }
    links.forEach(([a, b]) => {
      const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
      const force = (distance - 110) * springs;
      const ai = points.indexOf(a), bi = points.indexOf(b);
      forces[ai].x += dx / distance * force; forces[ai].y += dy / distance * force;
      forces[bi].x -= dx / distance * force; forces[bi].y -= dy / distance * force;
    });
    if (lens !== "constellation") {
      points.forEach((p, i) => {
        const t = target.get(p.id);
        if (t) { forces[i].x += (t.x - p.x) * pull; forces[i].y += (t.y - p.y) * pull; return; }
        // Role lens, no role: drift out to an outer ring, standing on their own.
        const r = Math.max(1, Math.hypot(p.x, p.y));
        const outward = (RING + 110 - r) * 0.03;
        forces[i].x += p.x / r * outward; forces[i].y += p.y / r * outward;
      });
    }
    points.forEach((p, i) => { p.x += forces[i].x; p.y += forces[i].y; });
    if (lens === "role") points.forEach((p) => { const a = roleAnchor.get(p.id); if (a) { p.x = a.x; p.y = a.y; } });
  }

  const extent = Math.max(180, ...points.flatMap((p) => [Math.abs(p.x), Math.abs(p.y)]));
  const toX = (x: number) => 450 + x / extent * 320, toY = (y: number) => 320 + y / extent * 230;
  points.forEach((p) => { p.x = toX(p.x); p.y = toY(p.y); });

  const territories: Territory[] = [];
  const region = (id: string, label: string, kind: EntityKind, cx: number, cy: number, members: string[]) => {
    const r = Math.min(240, Math.max(46, ...members.map((m) => { const p = byId.get(m)!; return Math.hypot(p.x - cx, p.y - cy) + 22; })));
    territories.push({ id, label, kind, x: cx, y: cy, r });
  };
  if (lens === "role") {
    roles.forEach((role) => {
      const members = nodes.filter((n) => homes.get(n.id)?.includes(role.id)).map((n) => n.id);
      const p = byId.get(role.id)!;
      region(role.id, role.title, "role", p.x, p.y, members);
    });
  }
  if (lens === "kind") {
    kinds.forEach((kind) => {
      const members = nodes.filter((n) => n.kind === kind).map((n) => n.id);
      const cx = members.reduce((s, m) => s + byId.get(m)!.x, 0) / members.length;
      const cy = members.reduce((s, m) => s + byId.get(m)!.y, 0) / members.length;
      region(kind, "", kind, cx, cy, members);
    });
  }
  return { positions: byId, territories };
}

/** Labels are useful until they overlap. Keep a stable, high-connection-first
 * subset and let selection always reveal the remaining title in the graph UI. */
export function visibleConstellationLabels(nodes: BrainNode[], positions: Map<string, ConstellationPoint>) {
  const occupied: Array<{ left: number; right: number; top: number; bottom: number }> = [];
  const visible = new Set<string>();
  [...nodes].sort((a, b) => {
    const degree = (positions.get(b.id)?.degree ?? 0) - (positions.get(a.id)?.degree ?? 0);
    return degree || a.title.localeCompare(b.title);
  }).forEach((node) => {
    const point = positions.get(node.id)!;
    const radius = 5 + Math.min(point.degree, 9) * 1.4;
    const width = Math.min(170, Math.max(64, node.title.length * 6.6));
    const box = { left: point.x - width / 2 - 8, right: point.x + width / 2 + 8, top: point.y + radius + 10, bottom: point.y + radius + 34 };
    if (occupied.some((other) => box.left < other.right && box.right > other.left && box.top < other.bottom && box.bottom > other.top)) return;
    occupied.push(box);
    visible.add(node.id);
  });
  return visible;
}
