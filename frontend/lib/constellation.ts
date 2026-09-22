import type { BrainNode, BrainEdge } from "./brain-graph";

export type ConstellationPoint = { id: string; x: number; y: number; degree: number };

/** Bounded, deterministic spring layout. Only confirmed edges exert attraction. */
export function constellation(nodes: BrainNode[], edges: BrainEdge[]) {
  const points = nodes.map((n, i) => ({ id: n.id, x: Math.cos(i * 2.39996) * (50 + Math.sqrt(i) * 35), y: Math.sin(i * 2.39996) * (50 + Math.sqrt(i) * 35), degree: 0 }));
  const byId = new Map(points.map((p) => [p.id, p]));
  const links = edges.map((e) => [byId.get(e.from)!, byId.get(e.to)!]).filter(([a, b]) => a && b);
  links.forEach(([a, b]) => { a.degree++; b.degree++; });
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
      const force = (distance - 110) * .025;
      const ai = points.indexOf(a), bi = points.indexOf(b);
      forces[ai].x += dx / distance * force; forces[ai].y += dy / distance * force;
      forces[bi].x -= dx / distance * force; forces[bi].y -= dy / distance * force;
    });
    points.forEach((p, i) => { p.x += forces[i].x; p.y += forces[i].y; });
  }
  const extent = Math.max(180, ...points.flatMap((p) => [Math.abs(p.x), Math.abs(p.y)]));
  points.forEach((p) => { p.x = 450 + p.x / extent * 320; p.y = 320 + p.y / extent * 230; });
  return byId;
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
