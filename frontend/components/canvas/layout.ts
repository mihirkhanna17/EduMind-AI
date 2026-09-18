import type { GraphEdge, GraphNode } from "@/lib/types";

export const WORLD_W = 2400;
export const WORLD_H = 1600;
export const NODE_W = 200;
export const NODE_H = 92;

export interface PlacedNode extends GraphNode {
  x: number;
  y: number;
}

/** Deterministic layered layout: prerequisite/parent depth → row, spread across width. */
export function layoutGraph(nodes: GraphNode[], edges: GraphEdge[]): PlacedNode[] {
  const incoming = new Map<number, number[]>();
  for (const e of edges) {
    incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
  }

  const depthCache = new Map<number, number>();
  const visiting = new Set<number>();
  function depth(id: number): number {
    if (depthCache.has(id)) return depthCache.get(id)!;
    if (visiting.has(id)) return 0; // cycle guard
    visiting.add(id);
    const parents = incoming.get(id) ?? [];
    const d = parents.length === 0 ? 0 : 1 + Math.max(...parents.map(depth));
    visiting.delete(id);
    depthCache.set(id, d);
    return d;
  }

  const rows = new Map<number, GraphNode[]>();
  for (const n of nodes) {
    const d = depth(n.id);
    rows.set(d, [...(rows.get(d) ?? []), n]);
  }

  const placed: PlacedNode[] = [];
  const rowKeys = [...rows.keys()].sort((a, b) => a - b);
  for (const d of rowKeys) {
    const row = rows.get(d)!.sort((a, b) => a.name.localeCompare(b.name));
    row.forEach((n, i) => {
      const x = ((i + 1) * WORLD_W) / (row.length + 1) - NODE_W / 2;
      // slight vertical stagger so long rows don't read as a rigid table
      const y = 120 + d * 230 + (i % 2 === 0 ? 0 : 26);
      placed.push({ ...n, x, y });
    });
  }
  return placed;
}

/** Cubic bezier between two placed nodes (bottom of source → top of target). */
export function edgePath(source: PlacedNode, target: PlacedNode): string {
  const x1 = source.x + NODE_W / 2;
  const y1 = source.y + NODE_H;
  const x2 = target.x + NODE_W / 2;
  const y2 = target.y;
  const bend = Math.max(40, (y2 - y1) * 0.5);
  return `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
}

/** Neighbor set for focus mode: the node plus everything sharing an edge. */
export function neighborhood(conceptId: number, edges: GraphEdge[]): Set<number> {
  const keep = new Set([conceptId]);
  for (const e of edges) {
    if (e.source === conceptId) keep.add(e.target);
    if (e.target === conceptId) keep.add(e.source);
  }
  return keep;
}
