import type { BrainNode, BrainEdge } from "./brain-graph";

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
