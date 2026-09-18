"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { branchHistory, continueBranch } from "@/lib/api";
import { mdToHtml } from "@/lib/markdown";
import type { BranchInfo, Diagram, Simulation } from "@/lib/types";
import DiagramViewer from "./DiagramViewer";

export interface PanelItem {
  key: string;
  kind: "diagram" | "simulation" | "branch";
  conceptId?: number;
  diagram?: Diagram;
  simulation?: Simulation;
  branch?: BranchInfo & { response: string };
}

const spawn = {
  initial: { opacity: 0, x: 24, scale: 0.97 },
  animate: { opacity: 1, x: 0, scale: 1 },
  exit: { opacity: 0, x: 24, scale: 0.97 },
  transition: { type: "spring" as const, stiffness: 260, damping: 26 },
};

function CardShell({
  label,
  tone,
  onHide,
  children,
  actions,
}: {
  label: string;
  tone: string;
  onHide: () => void;
  children: React.ReactNode;
  actions?: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <motion.div {...spawn} layout className="card" style={{ overflow: "hidden", flexShrink: 0 }}>
      <div
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 8,
          padding: "9px 12px",
          borderBottom: open ? "1px solid var(--border)" : "none",
          background: "var(--surface-2)",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <span style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: tone, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {open ? "▾" : "▸"} {label}
        </span>
        <span style={{ display: "flex", gap: 2, flexShrink: 0 }} onClick={(e) => e.stopPropagation()}>
          {actions}
          <button
            className="btn btn-ghost"
            onClick={onHide}
            title="Hide — restore anytime from the row below"
            style={{ padding: "0 6px", fontSize: 14, lineHeight: 1 }}
          >
            ×
          </button>
        </span>
      </div>
      {open && children}
    </motion.div>
  );
}

/* ── Branch: a forked side-thread, resumable forever ── */

function BranchCard({
  item,
  onHide,
  onMakeMain,
}: {
  item: PanelItem;
  onHide: () => void;
  onMakeMain?: () => void;
}) {
  const branch = item.branch!;
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([
    { role: "user", content: branch.question },
    { role: "bot", content: branch.response ?? "" },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    branchHistory(branch.branch_id)
      .then((r) => {
        if (r.messages.length > 2) setMessages(r.messages);
      })
      .catch(() => {});
  }, [branch.branch_id]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setBusy(true);
    try {
      const r = await continueBranch(branch.branch_id, text);
      setMessages((m) => [...m, { role: "bot", content: r.response }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <CardShell
      label={`⑂ ${branch.question.slice(0, 38)}${branch.question.length > 38 ? "…" : ""}`}
      tone="var(--accent-strong)"
      onHide={onHide}
      actions={
        onMakeMain && (
          <button
            className="btn btn-ghost"
            onClick={onMakeMain}
            title="Open as the main conversation"
            style={{ padding: "0 6px", fontSize: 12 }}
          >
            ⤢
          </button>
        )
      }
    >
      <div ref={scroller} style={{ maxHeight: 240, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {messages.map((m, i) => (
          <div
            key={i}
            className="markdown"
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "90%",
              padding: "7px 11px",
              borderRadius: 10,
              fontSize: 13,
              background: m.role === "user" ? "var(--accent-dim)" : "var(--surface-2)",
              color: m.role === "user" ? "var(--accent-strong)" : "var(--ink-2)",
            }}
            dangerouslySetInnerHTML={{ __html: mdToHtml(m.content) }}
          />
        ))}
        {busy && <div style={{ fontSize: 12, color: "var(--ink-3)" }}>thinking…</div>}
      </div>
      <div style={{ display: "flex", gap: 6, padding: 10, borderTop: "1px solid var(--border)" }}>
        <input
          className="input"
          placeholder="Dig deeper…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          style={{ fontSize: 13, padding: "7px 10px" }}
        />
        <button className="btn btn-primary" onClick={send} disabled={busy || !input.trim()} style={{ padding: "7px 12px" }}>
          ↳
        </button>
      </div>
    </CardShell>
  );
}

/* ── The panel ── */

export default function SidePanel({
  items,
  hiddenKeys,
  onHide,
  onRestore,
  onBranchFromDiagram,
  onRegenerateSim,
  onMakeBranchMain,
}: {
  items: PanelItem[];
  hiddenKeys: Set<string>;
  onHide: (key: string) => void;
  onRestore: (key: string) => void;
  onBranchFromDiagram: (context: string) => void;
  onRegenerateSim: (item: PanelItem) => void;
  onMakeBranchMain: (item: PanelItem) => void;
}) {
  const visible = items.filter((i) => !hiddenKeys.has(i.key));
  const hidden = items.filter((i) => hiddenKeys.has(i.key));

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: 14,
          display: "flex",
          flexDirection: "column",
          gap: 12,
        }}
      >
        {visible.length === 0 ? (
          <div style={{ color: "var(--ink-3)", fontSize: 13, textAlign: "center", paddingTop: 40 }}>
            Branches, visuals & simulations
            <br />
            for the open concept appear here.
          </div>
        ) : (
          <AnimatePresence>
            {visible.map((item) =>
              item.kind === "branch" ? (
                <BranchCard
                  key={item.key}
                  item={item}
                  onHide={() => onHide(item.key)}
                  onMakeMain={() => onMakeBranchMain(item)}
                />
              ) : item.kind === "diagram" ? (
                <CardShell key={item.key} label={`◫ ${item.diagram!.source} image`} tone="var(--series-3)" onHide={() => onHide(item.key)}>
                  <div style={{ padding: 10 }}>
                    <DiagramViewer diagram={item.diagram!} onBranch={onBranchFromDiagram} />
                  </div>
                </CardShell>
              ) : (
                <CardShell
                  key={item.key}
                  label={`⚙ simulation · ${item.simulation!.library}.js`}
                  tone="var(--series-4)"
                  onHide={() => onHide(item.key)}
                  actions={
                    <button
                      className="btn btn-ghost"
                      onClick={() => onRegenerateSim(item)}
                      title="Messy? Regenerate this simulation"
                      style={{ padding: "0 6px", fontSize: 12 }}
                    >
                      ↻
                    </button>
                  }
                >
                  <iframe
                    srcDoc={item.simulation!.code}
                    sandbox="allow-scripts"
                    title={`simulation-${item.simulation!.simulation_id}`}
                    style={{ width: "100%", height: 320, border: 0, display: "block", background: "#111827" }}
                  />
                </CardShell>
              )
            )}
          </AnimatePresence>
        )}
      </div>

      {/* hidden items — nothing is ever lost */}
      {hidden.length > 0 && (
        <div style={{ borderTop: "1px solid var(--border)", padding: "8px 12px" }}>
          <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 6 }}>
            Hidden — click to restore
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {hidden.map((item) => (
              <button
                key={item.key}
                className="chip"
                onClick={() => onRestore(item.key)}
                style={{ cursor: "pointer", padding: "4px 10px", border: "1px dashed var(--border-strong)", background: "transparent" }}
              >
                {item.kind === "branch"
                  ? `⑂ ${item.branch!.question.slice(0, 24)}…`
                  : item.kind === "diagram"
                    ? "◫ image"
                    : "⚙ simulation"}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
