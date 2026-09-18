"use client";

import { motion } from "framer-motion";
import { masteryColor } from "@/lib/session";
import { NODE_H, NODE_W, type PlacedNode } from "./layout";

interface Props {
  node: PlacedNode;
  selected: boolean;
  dimmed: boolean;
  onSelect: (node: PlacedNode) => void;
}

/** Custom concept card: mastery drives the fill of the left accent bar and the
 * halo; confidence drives the progress ring. Sequential ramp — magnitude, not
 * a green/red verdict. */
export default function ConceptNode({ node, selected, dimmed, onSelect }: Props) {
  const fill = masteryColor(node.mastery);
  const conf = Math.round(node.confidence * 100);
  const unresolved = (node.misconceptions ?? []).filter((m) => !m.resolved).length;
  const ringR = 15;
  const ringC = 2 * Math.PI * ringR;

  return (
    <motion.div
      id={`concept-${node.id}`}
      className="no-pan"
      onClick={() => onSelect(node)}
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{
        opacity: dimmed ? 0.14 : 1,
        scale: selected ? 1.04 : 1,
        filter: dimmed ? "blur(1.5px)" : "blur(0px)",
      }}
      transition={{ type: "spring", stiffness: 260, damping: 24 }}
      style={{
        position: "absolute",
        left: node.x,
        top: node.y,
        width: NODE_W,
        height: NODE_H,
        borderRadius: 14,
        background: "var(--surface)",
        border: `1px solid ${selected ? "var(--accent)" : "var(--border-strong)"}`,
        boxShadow: selected
          ? `0 0 0 3px var(--accent-dim), var(--shadow-2)`
          : `var(--shadow-1)`,
        cursor: "pointer",
        display: "flex",
        overflow: "hidden",
        userSelect: "none",
      }}
    >
      {/* mastery bar */}
      <div style={{ width: 6, background: fill, flexShrink: 0 }} />

      <div style={{ padding: "10px 12px", flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 650,
            lineHeight: 1.25,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {node.name}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 7 }}>
          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>
            mastery {Math.round(node.mastery * 100)}%
          </span>
          {unresolved > 0 && (
            <span
              title={`${unresolved} unresolved misconception${unresolved > 1 ? "s" : ""}`}
              style={{
                fontSize: 10.5,
                fontWeight: 700,
                color: "#101018",
                background: "var(--warning)",
                borderRadius: 999,
                padding: "0 6px",
                lineHeight: "16px",
              }}
            >
              {unresolved}
            </span>
          )}
        </div>
      </div>

      {/* confidence ring */}
      <div style={{ display: "grid", placeItems: "center", paddingRight: 10 }}>
        <svg width="38" height="38" viewBox="0 0 38 38" aria-label={`confidence ${conf}%`}>
          <circle cx="19" cy="19" r={ringR} fill="none" stroke="var(--surface-3)" strokeWidth="3.5" />
          <circle
            cx="19"
            cy="19"
            r={ringR}
            fill="none"
            stroke={fill === "var(--mastery-0)" ? "var(--mastery-2)" : fill}
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeDasharray={`${(conf / 100) * ringC} ${ringC}`}
            transform="rotate(-90 19 19)"
            style={{ transition: "stroke-dasharray 600ms ease" }}
          />
          <text x="19" y="22" textAnchor="middle" fontSize="9.5" fontWeight="700" fill="var(--ink-2)">
            {conf}
          </text>
        </svg>
      </div>
    </motion.div>
  );
}
