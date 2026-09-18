"use client";

import { useMemo, useRef, useState } from "react";
import {
  TransformComponent,
  TransformWrapper,
  type ReactZoomPanPinchContentRef,
} from "react-zoom-pan-pinch";
import type { GraphEdge, GraphNode } from "@/lib/types";
import ConceptNode from "./ConceptNode";
import {
  NODE_H,
  NODE_W,
  WORLD_H,
  WORLD_W,
  edgePath,
  layoutGraph,
  neighborhood,
  type PlacedNode,
} from "./layout";

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: number | null;
  focusMode: boolean;
  onSelect: (node: PlacedNode) => void;
}

const MINI_W = 200;
const MINI_H = 132;

export default function KnowledgeCanvas({ nodes, edges, selectedId, focusMode, onSelect }: Props) {
  const placed = useMemo(() => layoutGraph(nodes, edges), [nodes, edges]);
  const byId = useMemo(() => new Map(placed.map((n) => [n.id, n])), [placed]);
  const wrapperRef = useRef<ReactZoomPanPinchContentRef>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ scale: 0.55, x: 0, y: 0 });

  const focusSet = useMemo(
    () => (focusMode && selectedId ? neighborhood(selectedId, edges) : null),
    [focusMode, selectedId, edges]
  );

  const vp = viewportRef.current?.getBoundingClientRect();
  const miniScale = MINI_W / WORLD_W;
  const viewRect = vp
    ? {
        x: (-view.x / view.scale) * miniScale,
        y: (-view.y / view.scale) * miniScale,
        w: (vp.width / view.scale) * miniScale,
        h: (vp.height / view.scale) * miniScale,
      }
    : null;

  return (
    <div ref={viewportRef} style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <TransformWrapper
        ref={wrapperRef}
        minScale={0.25}
        maxScale={2.5}
        initialScale={0.55}
        initialPositionX={-WORLD_W * 0.55 * 0.5 + 400}
        initialPositionY={-40}
        limitToBounds={false}
        doubleClick={{ disabled: true }}
        panning={{ excluded: ["no-pan", "input", "textarea", "button"] }}
        onTransform={(_, s) => setView({ scale: s.scale, x: s.positionX, y: s.positionY })}
      >
        <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
          <div
            style={{
              width: WORLD_W,
              height: WORLD_H,
              position: "relative",
              backgroundImage:
                "radial-gradient(circle, rgba(255,255,255,0.05) 1px, transparent 1px)",
              backgroundSize: "36px 36px",
            }}
          >
            {/* edge layer — custom cubic beziers, under the nodes */}
            <svg
              width={WORLD_W}
              height={WORLD_H}
              style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
            >
              <defs>
                <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                  <path d="M 0 1 L 7 4 L 0 7 z" fill="rgba(144,133,233,0.5)" />
                </marker>
              </defs>
              {edges.map((e, i) => {
                const s = byId.get(e.source);
                const t = byId.get(e.target);
                if (!s || !t) return null;
                const inFocus =
                  !focusSet || (focusSet.has(e.source) && focusSet.has(e.target));
                return (
                  <path
                    key={i}
                    d={edgePath(s, t)}
                    fill="none"
                    stroke={
                      e.kind === "prerequisite"
                        ? "rgba(144,133,233,0.45)"
                        : "rgba(255,255,255,0.14)"
                    }
                    strokeWidth={e.kind === "prerequisite" ? 2 : 1.5}
                    strokeDasharray={e.kind === "parent" ? "5 5" : undefined}
                    markerEnd={e.kind === "prerequisite" ? "url(#arrow)" : undefined}
                    opacity={inFocus ? 1 : 0.08}
                    style={{ transition: "opacity 300ms ease" }}
                  />
                );
              })}
            </svg>

            {/* concept nodes */}
            {placed.map((n) => (
              <ConceptNode
                key={n.id}
                node={n}
                selected={n.id === selectedId}
                dimmed={!!focusSet && !focusSet.has(n.id)}
                onSelect={(node) => {
                  onSelect(node);
                  wrapperRef.current?.zoomToElement(`concept-${node.id}`, 1.0, 350);
                }}
              />
            ))}
          </div>
        </TransformComponent>
      </TransformWrapper>

      {/* minimap */}
      <div
        style={{
          position: "absolute",
          right: 16,
          bottom: 16,
          width: MINI_W,
          height: MINI_H,
          borderRadius: 10,
          background: "rgba(13,13,15,0.85)",
          border: "1px solid var(--border-strong)",
          backdropFilter: "blur(6px)",
          overflow: "hidden",
        }}
      >
        <svg width={MINI_W} height={MINI_H} viewBox={`0 0 ${MINI_W} ${WORLD_H * miniScale}`}>
          {placed.map((n) => (
            <rect
              key={n.id}
              x={n.x * miniScale}
              y={n.y * miniScale}
              width={NODE_W * miniScale}
              height={NODE_H * miniScale}
              rx="1.5"
              fill={
                n.id === selectedId
                  ? "var(--accent)"
                  : focusSet && !focusSet.has(n.id)
                    ? "rgba(255,255,255,0.10)"
                    : "rgba(109,167,236,0.7)"
              }
            />
          ))}
          {viewRect && (
            <rect
              x={viewRect.x}
              y={viewRect.y}
              width={viewRect.w}
              height={viewRect.h}
              fill="none"
              stroke="rgba(255,255,255,0.55)"
              strokeWidth="1.5"
              rx="2"
            />
          )}
        </svg>
      </div>
    </div>
  );
}
