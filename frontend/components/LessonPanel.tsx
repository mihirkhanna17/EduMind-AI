"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  chat,
  fetchWebImage,
  generateDiagram,
  getPlan,
  getSimulation,
  getStoredLesson,
  openBranch,
  streamLesson,
  uploadImage,
  type PlanEntry,
  type VisualSuggestion,
} from "@/lib/api";
import { mdToHtml } from "@/lib/markdown";
import type { Diagram, LessonBlock } from "@/lib/types";
import type { PlacedNode } from "./canvas/layout";
import type { PanelItem } from "./SidePanel";
import AssessmentPanel from "./AssessmentPanel";
import DiagramViewer from "./DiagramViewer";

const BLOCK_LABELS: Record<string, string> = {
  intuition: "Intuition",
  analogy: "Analogy",
  theory: "Theory",
  real_world_example: "In the real world",
  counter_example: "Where it breaks",
  interactive_question: "Your turn",
  summary: "Takeaways",
};

interface Props {
  userId: number;
  sessionId: number;
  subject: string;
  concept: PlacedNode | null;
  onSpawnExtra: (extra: Omit<PanelItem, "key">) => void;
  onGraphChanged: () => void;
  onSelectConcept: (conceptId: number) => void;
  onSelectConceptByName: (name: string) => void;
  onOpenMap: () => void;
  onBlocksReady: (firstBlockId: number | null) => void;
}

export default function LessonPanel({
  userId,
  sessionId,
  subject,
  concept,
  onSpawnExtra,
  onGraphChanged,
  onSelectConcept,
  onSelectConceptByName,
  onOpenMap,
  onBlocksReady,
}: Props) {
  const [tab, setTab] = useState<"lesson" | "quiz">("lesson");
  const [blocks, setBlocks] = useState<LessonBlock[]>([]);
  const [restored, setRestored] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [branchFor, setBranchFor] = useState<number | null>(null);
  const [branchQ, setBranchQ] = useState("");
  const [visualQ, setVisualQ] = useState("");
  const [visualOpen, setVisualOpen] = useState(false);
  const [chatLog, setChatLog] = useState<{ role: string; content: string }[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [plan, setPlan] = useState<PlanEntry[]>([]);
  const [visualSuggestion, setVisualSuggestion] = useState<VisualSuggestion | null>(null);
  const [inlineDiagrams, setInlineDiagrams] = useState<Diagram[]>([]);
  const pendingTeach = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const chatKey = `edumind.chat.${userId}.${subject}`;

  /* ── persistence: chat survives reloads; lessons restore from the DB ── */

  useEffect(() => {
    try {
      const saved = localStorage.getItem(chatKey);
      if (saved) setChatLog(JSON.parse(saved));
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatKey]);

  useEffect(() => {
    if (chatLog.length) localStorage.setItem(chatKey, JSON.stringify(chatLog.slice(-60)));
  }, [chatLog, chatKey]);

  const refreshPlan = useCallback(() => {
    getPlan(userId, subject).then((r) => setPlan(r.plan)).catch(() => {});
  }, [userId, subject]);

  useEffect(refreshPlan, [refreshPlan]);

  // On selecting a concept: restore its last stored lesson (no model call),
  // or auto-teach if the "Continue" flow queued it.
  useEffect(() => {
    setBlocks([]);
    setRestored(false);
    setBranchFor(null);
    setInlineDiagrams([]);
    setVisualSuggestion(null);
    onBlocksReady(null);
    if (!concept) return;
    if (pendingTeach.current) {
      pendingTeach.current = false;
      void teach(concept.id);
      return;
    }
    getStoredLesson(userId, concept.id)
      .then((r) => {
        if (r.blocks.length) {
          setBlocks(r.blocks);
          setRestored(true);
          onBlocksReady(r.blocks[0].id);
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [concept?.id]);

  useEffect(() => {
    chatEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatLog, busy]);

  async function teach(conceptId?: number) {
    const id = conceptId ?? concept?.id;
    if (!id || streaming) return;
    setBlocks([]);
    setRestored(false);
    setStreamText("");
    setVisualSuggestion(null);
    setStreaming(true);
    try {
      const done = await streamLesson(
        userId,
        sessionId,
        id,
        (text, replace) => setStreamText((prev) => (replace ? text : prev + text)),
        (suggestion) => {
          // the agent judges image & simulation independently — both can fire
          if (suggestion.image) {
            void autoFetchDiagram(suggestion.image_query, id); // no asking — just show it
          }
          if (suggestion.simulation) {
            setVisualSuggestion(suggestion); // simulations are heavier → one-click chip
          }
        }
      );
      setBlocks(done);
      setStreamText("");
      if (done.length) onBlocksReady(done[0].id);
      onGraphChanged();
      refreshPlan();
    } catch (e) {
      setStreamText(`⚠ ${(e as Error).message}`);
    } finally {
      setStreaming(false);
    }
  }

  /* auto-sourced visual: try a real web image, fall back to drawing a schematic */
  async function autoFetchDiagram(query: string, conceptId: number) {
    setBusy("visual");
    try {
      let d: Diagram;
      try {
        d = await fetchWebImage(query, conceptId);
      } catch {
        d = await generateDiagram(query, conceptId);
      }
      setInlineDiagrams((ds) => [...ds, d]); // straight into the main chat
      onSpawnExtra({ kind: "diagram", conceptId, diagram: d }); // and the workspace
    } catch {
      /* visual is a bonus — never fail the lesson over it */
    } finally {
      setBusy(null);
    }
  }

  /* the visualization-need agent suggested a simulation — one click accepts */
  async function acceptVisual() {
    if (!visualSuggestion || !concept) return;
    setVisualSuggestion(null);
    await simulate();
  }

  /* crop/region "Go deeper" → real branch anchored to this lesson */
  async function branchFromContext(context: string) {
    if (!blocks.length) return;
    setBusy("branch");
    try {
      const r = await openBranch({
        user_id: userId,
        session_id: sessionId,
        parent_block_id: blocks[0].id,
        question: `Go deeper on this part of the diagram — ${context.slice(0, 300)}`,
      });
      onSpawnExtra({ kind: "branch", conceptId: concept?.id, branch: r });
    } finally {
      setBusy(null);
    }
  }

  function teachByName(name: string) {
    pendingTeach.current = true;
    onSelectConceptByName(name);
  }

  /* select text inside a block → prefill a branch question about it */
  function captureSelection(block: LessonBlock) {
    const sel = window.getSelection()?.toString().trim();
    if (sel && sel.length > 3) {
      setBranchFor(block.id);
      setBranchQ(`About “${sel.slice(0, 140)}” — `);
    }
  }

  async function submitBranch(block: LessonBlock) {
    const question = branchQ.trim();
    if (!question) return;
    setBusy("branch");
    try {
      const r = await openBranch({
        user_id: userId,
        session_id: sessionId,
        parent_block_id: block.id,
        question,
      });
      onSpawnExtra({ kind: "branch", conceptId: concept?.id, branch: r });
      setBranchFor(null);
      setBranchQ("");
    } finally {
      setBusy(null);
    }
  }

  async function simulate() {
    if (!concept) return;
    setBusy("sim");
    try {
      const sim = await getSimulation(userId, concept.id);
      onSpawnExtra({ kind: "simulation", conceptId: concept.id, simulation: sim });
    } finally {
      setBusy(null);
    }
  }

  async function visual(kind: "fetch" | "generate") {
    const q = visualQ.trim() || concept?.name || "";
    if (!q) return;
    setBusy("visual");
    try {
      const d =
        kind === "fetch"
          ? await fetchWebImage(q, concept?.id)
          : await generateDiagram(q, concept?.id);
      onSpawnExtra({ kind: "diagram", conceptId: concept?.id, diagram: d });
      setVisualOpen(false);
      setVisualQ("");
    } catch (e) {
      setChatLog((l) => [...l, { role: "bot", content: `⚠ ${(e as Error).message}` }]);
    } finally {
      setBusy(null);
    }
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy("visual");
    try {
      const d = await uploadImage(file, concept?.id);
      onSpawnExtra({ kind: "diagram", conceptId: concept?.id, diagram: d });
    } finally {
      setBusy(null);
      e.target.value = "";
    }
  }

  async function sendChat() {
    const text = chatInput.trim();
    if (!text || busy === "chat") return;
    setChatInput("");
    setChatLog((l) => [...l, { role: "user", content: text }]);
    setBusy("chat");
    try {
      const r = await chat({
        user_id: userId,
        session_id: sessionId,
        message: text,
        concept_id: concept?.id ?? null,
      });
      setChatLog((l) => [...l, { role: "bot", content: r.response }]);
      if (["assess", "revise", "end_session"].includes(r.mode)) onGraphChanged();
    } catch (e) {
      setChatLog((l) => [...l, { role: "bot", content: `⚠ ${(e as Error).message}` }]);
    } finally {
      setBusy(null);
    }
  }

  /* "what next" from the deterministic plan */
  const upNext = plan.filter((p) => p.status === "ready" && p.concept_id !== concept?.id).slice(0, 3);

  function continueTo(entry: PlanEntry) {
    pendingTeach.current = true;
    onSelectConcept(entry.concept_id);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* header */}
      <div style={{ padding: "14px 18px 0" }}>
        <div style={{ fontSize: 11.5, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink-3)" }}>
          {concept ? concept.name : "No concept selected"}
        </div>
        <div style={{ display: "flex", gap: 6, margin: "10px 0" }}>
          {(["lesson", "quiz"] as const).map((t) => (
            <button
              key={t}
              className="btn"
              onClick={() => setTab(t)}
              style={{
                padding: "5px 14px",
                fontSize: 13,
                background: tab === t ? "var(--accent-dim)" : "transparent",
                borderColor: tab === t ? "var(--accent)" : "var(--border)",
                color: tab === t ? "var(--accent-strong)" : "var(--ink-2)",
              }}
            >
              {t === "lesson" ? "Lesson" : "Diagnostic"}
            </button>
          ))}
        </div>
      </div>

      {/* body */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0 18px 18px" }}>
        {tab === "quiz" ? (
          <AssessmentPanel
            userId={userId}
            subject={subject}
            onFinished={() => {
              onGraphChanged();
              refreshPlan();
            }}
            onTeach={(name) => {
              setTab("lesson");
              teachByName(name);
            }}
          />
        ) : (
          <>
            {/* study plan strip — always visible so "what next" needs no asking */}
            {upNext.length > 0 && (
              <div className="card" style={{ padding: "10px 12px", marginBottom: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-3)", marginBottom: 7 }}>
                  Up next in your plan
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {upNext.map((p, i) => (
                    <button
                      key={p.concept_id}
                      className="chip"
                      onClick={() => continueTo(p)}
                      title={p.prerequisites.length ? `builds on ${p.prerequisites.join(", ")}` : "no prerequisites"}
                      style={{
                        cursor: "pointer",
                        border: "1px solid",
                        borderColor: i === 0 ? "var(--accent)" : "transparent",
                        background: i === 0 ? "var(--accent-dim)" : "var(--surface-3)",
                        color: i === 0 ? "var(--accent-strong)" : "var(--ink-2)",
                        padding: "6px 12px",
                      }}
                    >
                      {i === 0 ? "▶ " : ""}{p.name}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {!concept ? (
              <div style={{ color: "var(--ink-2)", fontSize: 14 }}>
                Hit <b>▶</b> above and Edumind walks you through your plan in order — or{" "}
                <button className="btn" onClick={onOpenMap} style={{ padding: "3px 10px", fontSize: 13 }}>
                  🗺 open the map
                </button>{" "}
                to pick a concept yourself.
              </div>
            ) : (
              <>
                {/* action bar */}
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                  <button
                    className="btn btn-primary"
                    onClick={() => teach()}
                    disabled={streaming}
                    title={blocks.length ? "Generate a brand-new lesson for this topic" : undefined}
                    style={{ fontSize: 13 }}
                  >
                    {streaming ? "Teaching…" : blocks.length ? "↻ Start fresh" : "Teach me this"}
                  </button>
                  <button className="btn" onClick={simulate} disabled={busy === "sim"} style={{ fontSize: 13 }}>
                    {busy === "sim" ? "Building…" : "⚙ Simulate"}
                  </button>
                  <button className="btn" onClick={() => setVisualOpen((v) => !v)} style={{ fontSize: 13 }}>
                    ◫ Visualize
                  </button>
                </div>

                <AnimatePresence>
                  {visualOpen && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="card"
                      style={{ padding: 12, marginBottom: 12, overflow: "hidden" }}
                    >
                      <input
                        className="input"
                        placeholder={`e.g. "${concept.name} labelled diagram"`}
                        value={visualQ}
                        onChange={(e) => setVisualQ(e.target.value)}
                        style={{ fontSize: 13, marginBottom: 8 }}
                      />
                      <div style={{ display: "flex", gap: 6 }}>
                        <button className="btn" onClick={() => visual("fetch")} disabled={busy === "visual"} style={{ fontSize: 12.5 }}>
                          Fetch real image
                        </button>
                        <button className="btn" onClick={() => visual("generate")} disabled={busy === "visual"} style={{ fontSize: 12.5 }}>
                          Draw schematic
                        </button>
                        <button className="btn" onClick={() => fileInput.current?.click()} disabled={busy === "visual"} style={{ fontSize: 12.5 }}>
                          Upload
                        </button>
                        <input ref={fileInput} type="file" accept="image/*" hidden onChange={onUpload} />
                      </div>
                      {busy === "visual" && (
                        <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 8 }}>
                          Sourcing & segmenting regions (one-time vision pass)…
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                {restored && blocks.length > 0 && (
                  <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 8 }}>
                    ↺ Restored your last lesson on this concept
                  </div>
                )}

                {streaming && (
                  <div className="card" style={{ padding: 14, fontSize: 13, color: "var(--ink-2)", whiteSpace: "pre-wrap", fontFamily: "var(--mono)", maxHeight: 300, overflowY: "auto" }}>
                    {streamText || "Thinking about the best way to teach you this…"}
                  </div>
                )}

                {!streaming &&
                  blocks.map((b, i) => (
                    <motion.div
                      key={b.id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.05 }}
                      className="card"
                      style={{ padding: "14px 16px", marginBottom: 10, position: "relative" }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: b.type === "interactive_question" ? "var(--accent-strong)" : "var(--ink-3)" }}>
                          {BLOCK_LABELS[b.type] ?? b.type}
                        </span>
                        <button
                          className="btn btn-ghost"
                          title="Branch off — or select any text in this block to ask about it"
                          onClick={() => setBranchFor(branchFor === b.id ? null : b.id)}
                          style={{ padding: "2px 8px", fontSize: 12 }}
                        >
                          ⑂ ask
                        </button>
                      </div>
                      <div
                        className="markdown"
                        onMouseUp={() => captureSelection(b)}
                        style={{ fontSize: 14, color: "var(--ink-2)" }}
                        dangerouslySetInnerHTML={{ __html: mdToHtml(b.content) }}
                      />
                      <AnimatePresence>
                        {branchFor === b.id && (
                          <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            style={{ overflow: "hidden" }}
                          >
                            <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                              <input
                                className="input"
                                autoFocus
                                placeholder="Wait — why…?  (tip: select text above to quote it)"
                                value={branchQ}
                                onChange={(e) => setBranchQ(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && submitBranch(b)}
                                style={{ fontSize: 13, padding: "7px 10px" }}
                              />
                              <button className="btn btn-primary" disabled={busy === "branch" || !branchQ.trim()} onClick={() => submitBranch(b)} style={{ padding: "7px 12px", fontSize: 13 }}>
                                {busy === "branch" ? "…" : "⑂"}
                              </button>
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </motion.div>
                  ))}

                {/* the visualization-need agent thinks this is better seen */}
                <AnimatePresence>
                  {!streaming && visualSuggestion && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="card"
                      style={{
                        padding: "10px 14px",
                        marginBottom: 10,
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        borderColor: "var(--accent)",
                        background: "var(--accent-dim)",
                      }}
                    >
                      <span style={{ fontSize: 13.5, color: "var(--accent-strong)" }}>
                        This topic is better <b>seen</b> than read — want an interactive simulation?
                      </span>
                      <button
                        className="btn btn-primary"
                        onClick={acceptVisual}
                        disabled={busy === "visual" || busy === "sim"}
                        style={{ marginLeft: "auto", fontSize: 12.5, padding: "5px 12px" }}
                      >
                        {busy === "visual" || busy === "sim" ? "Building…" : "Show me"}
                      </button>
                      <button className="btn btn-ghost" onClick={() => setVisualSuggestion(null)} style={{ padding: "2px 8px", fontSize: 13 }}>
                        ×
                      </button>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* auto-sourced diagrams — shown right in the main chat */}
                {!streaming && busy === "visual" && (
                  <div className="card" style={{ padding: "10px 14px", marginBottom: 10, fontSize: 13, color: "var(--ink-3)" }}>
                    ◫ This topic teaches better with a diagram — fetching one…
                  </div>
                )}
                {!streaming &&
                  inlineDiagrams.map((d) => (
                    <motion.div
                      key={d.diagram_id}
                      initial={{ opacity: 0, y: 12 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="card"
                      style={{ padding: 12, marginBottom: 10 }}
                    >
                      <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "var(--series-3)", marginBottom: 8 }}>
                        ◫ visual — sourced automatically ({d.source})
                      </div>
                      <DiagramViewer diagram={d} onBranch={branchFromContext} />
                    </motion.div>
                  ))}

                {/* continue flow — the plan drives the next step automatically */}
                {!streaming && blocks.length > 0 && upNext.length > 0 && (
                  <button className="btn" onClick={() => continueTo(upNext[0])} style={{ width: "100%", justifyContent: "center", fontSize: 13.5, marginTop: 4 }}>
                    Continue → {upNext[0].name}
                  </button>
                )}
              </>
            )}

            {/* chat transcript */}
            {chatLog.length > 0 && (
              <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
                {chatLog.map((m, i) => (
                  <div
                    key={i}
                    style={{
                      alignSelf: m.role === "user" ? "flex-end" : "flex-start",
                      maxWidth: "92%",
                      padding: "8px 12px",
                      borderRadius: 10,
                      fontSize: 13.5,
                      background: m.role === "user" ? "var(--accent-dim)" : "var(--surface-2)",
                      color: m.role === "user" ? "var(--accent-strong)" : "var(--ink-2)",
                    }}
                    className="markdown"
                    dangerouslySetInnerHTML={{ __html: mdToHtml(m.content) }}
                  />
                ))}
                {busy === "chat" && <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>thinking…</div>}
                <div ref={chatEnd} />
              </div>
            )}
          </>
        )}
      </div>

      {/* chat bar */}
      <div style={{ display: "flex", gap: 8, padding: 14, borderTop: "1px solid var(--border)" }}>
        <input
          className="input"
          placeholder="Ask anything — on-topic or not, Edumind answers what you asked…"
          value={chatInput}
          onChange={(e) => setChatInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendChat()}
        />
        <button className="btn btn-primary" onClick={sendChat} disabled={busy === "chat" || !chatInput.trim()}>
          ↑
        </button>
      </div>
    </div>
  );
}
