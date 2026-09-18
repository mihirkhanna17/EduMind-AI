"use client";

import { AnimatePresence, motion } from "framer-motion";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import BranchMain from "@/components/BranchMain";
import KnowledgeCanvas from "@/components/canvas/KnowledgeCanvas";
import { layoutGraph, type PlacedNode } from "@/components/canvas/layout";
import LessonPanel from "@/components/LessonPanel";
import SidePanel, { type PanelItem } from "@/components/SidePanel";
import {
  branchesForConcept,
  cachedSimulation,
  deleteBranch,
  endSession,
  fetchGraph,
  getProfile,
  getSimulation,
  imagesForConcept,
  openBranch,
  startSession,
} from "@/lib/api";
import { clearUser, loadSubject, loadUser, masteryColor, saveSubject } from "@/lib/session";
import type { GraphEdge, GraphNode, User } from "@/lib/types";

type MainView = { type: "lesson" } | { type: "branch"; item: PanelItem };

export default function LearnPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [subject, setSubject] = useState<string>("");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [panelItems, setPanelItems] = useState<PanelItem[]>([]);
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<PlacedNode | null>(null);
  const [mainView, setMainView] = useState<MainView>({ type: "lesson" });
  const [firstBlockId, setFirstBlockId] = useState<number | null>(null);
  const [showMap, setShowMap] = useState(false);
  const [focusMode, setFocusMode] = useState(false);
  const [ending, setEnding] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [subjectMenu, setSubjectMenu] = useState(false);
  const [allSubjects, setAllSubjects] = useState<string[]>([]);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatText, setNewChatText] = useState("");

  const refreshGraph = useCallback(async (uid: number, subj: string) => {
    try {
      const g = await fetchGraph(uid, subj);
      setNodes(g.nodes);
      setEdges(g.edges);
      setApiError(null);
    } catch (e) {
      setApiError((e as Error).message);
    }
  }, []);

  const connect = useCallback(
    (u: User, s: string) => {
      refreshGraph(u.id, s);
      startSession(u.id)
        .then((r) => {
          setSessionId(r.session_id);
          setApiError(null);
        })
        .catch((e) => setApiError((e as Error).message));
    },
    [refreshGraph]
  );

  useEffect(() => {
    const u = loadUser();
    if (!u) return void router.replace("/");
    const s = loadSubject(u.id);
    if (!s) return void router.replace("/onboarding");
    setUser(u);
    setSubject(s);
    connect(u, s);
    getProfile(u.id).then((p) => setAllSubjects(p.subjects)).catch(() => {});
  }, [router, connect]);

  /* selecting a concept restores everything ever created under it */
  const openConcept = useCallback(
    async (node: PlacedNode) => {
      setSelected(node);
      setShowMap(false);
      setMainView({ type: "lesson" });
      setHiddenKeys(new Set());
      if (!user) return;
      try {
        const [branches, images, sim] = await Promise.all([
          branchesForConcept(node.id, user.id),
          imagesForConcept(node.id),
          cachedSimulation(user.id, node.id),
        ]);
        const restored: PanelItem[] = [
          ...branches.branches.map((b) => ({
            key: `branch-${b.branch_id}`,
            kind: "branch" as const,
            conceptId: node.id,
            branch: b,
          })),
          ...images.diagrams.map((d) => ({
            key: `diagram-${d.diagram_id}`,
            kind: "diagram" as const,
            conceptId: node.id,
            diagram: d,
          })),
          ...(sim.found
            ? [{ key: `sim-${sim.simulation_id}`, kind: "simulation" as const, conceptId: node.id, simulation: sim }]
            : []),
        ];
        setPanelItems(restored);
      } catch {
        setPanelItems([]);
      }
    },
    [user]
  );

  function selectConceptById(conceptId: number) {
    const placed = layoutGraph(nodes, edges).find((n) => n.id === conceptId);
    if (placed) void openConcept(placed);
  }

  function selectConceptByName(name: string) {
    const placed = layoutGraph(nodes, edges).find(
      (n) => n.name.toLowerCase() === name.toLowerCase()
    );
    if (placed) void openConcept(placed);
  }

  /* "Go deeper" from a workspace diagram → branch anchored to the open lesson */
  async function branchFromDiagram(context: string) {
    if (!user || !sessionId || !firstBlockId) return;
    const r = await openBranch({
      user_id: user.id,
      session_id: sessionId,
      parent_block_id: firstBlockId,
      question: `Go deeper on this part of the diagram — ${context.slice(0, 300)}`,
    });
    setPanelItems((xs) => [
      { key: `branch-${r.branch_id}`, kind: "branch", conceptId: selected?.id, branch: r },
      ...xs,
    ]);
  }

  /* free-form "new chat" under the open topic */
  async function startNewChat() {
    const text = newChatText.trim();
    if (!text || !user || !sessionId) return;
    setNewChatText("");
    setNewChatOpen(false);
    const r = await openBranch({
      user_id: user.id,
      session_id: sessionId,
      concept_id: selected?.id ?? null,
      question: text,
    });
    const item: PanelItem = {
      key: `branch-${r.branch_id}`,
      kind: "branch",
      conceptId: selected?.id,
      branch: r,
    };
    setPanelItems((xs) => [item, ...xs]);
    setMainView({ type: "branch", item });
  }

  async function removeBranch(item: PanelItem) {
    if (!item.branch) return;
    if (!confirm(`Delete branch "${item.branch.question.slice(0, 60)}"? This can't be undone.`)) return;
    await deleteBranch(item.branch.branch_id);
    setPanelItems((xs) => xs.filter((x) => x.key !== item.key));
    if (mainView.type === "branch" && mainView.item.key === item.key) {
      setMainView({ type: "lesson" });
    }
  }

  function switchSubject(s: string) {
    if (!user) return;
    saveSubject(user.id, s);
    window.location.reload(); // clean slate: new graph, new session
  }

  async function regenerateSim(item: PanelItem) {
    if (!user || !item.conceptId) return;
    const sim = await getSimulation(user.id, item.conceptId, true); // force
    setPanelItems((xs) =>
      xs.map((x) => (x.key === item.key ? { ...x, simulation: sim } : x))
    );
  }

  async function finishSession() {
    if (!sessionId || ending) return;
    setEnding(true);
    try {
      await endSession(sessionId); // triggers the batched Digital Twin update
      router.push("/dashboard");
    } finally {
      setEnding(false);
    }
  }

  if (!user) return null;

  const branchItems = panelItems.filter((i) => i.kind === "branch");
  const sortedTopics = [...nodes].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <main style={{ height: "100vh", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* top bar */}
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 18px",
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
          zIndex: 5,
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--accent)" }}>
          Edumind
        </span>
        <div style={{ position: "relative" }}>
          <button
            className="chip"
            onClick={() => setSubjectMenu((m) => !m)}
            title="Switch subject"
            style={{ cursor: "pointer", border: "1px solid var(--border-strong)", background: "var(--surface-3)" }}
          >
            {subject} ▾
          </button>
          {subjectMenu && (
            <div
              className="card"
              style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, zIndex: 60, minWidth: 200, padding: 6, boxShadow: "var(--shadow-2)" }}
            >
              {allSubjects.map((s) => (
                <button
                  key={s}
                  onClick={() => (s === subject ? setSubjectMenu(false) : switchSubject(s))}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 12px",
                    borderRadius: 6,
                    border: "none",
                    cursor: "pointer",
                    fontSize: 13.5,
                    background: s === subject ? "var(--accent-dim)" : "transparent",
                    color: s === subject ? "var(--accent-strong)" : "var(--ink)",
                  }}
                >
                  {s === subject ? "● " : ""}{s}
                </button>
              ))}
              <Link
                href="/onboarding"
                style={{ display: "block", padding: "8px 12px", fontSize: 13.5, color: "var(--cyan)", borderTop: "1px solid var(--border)", marginTop: 4 }}
              >
                ＋ Add a subject
              </Link>
            </div>
          )}
        </div>
        <div style={{ flex: 1 }} onClick={() => subjectMenu && setSubjectMenu(false)} />
        <button
          className="btn"
          onClick={() => setShowMap(true)}
          style={{ fontSize: 13, borderColor: "var(--accent)", color: "var(--accent-strong)" }}
        >
          🗺 Knowledge map
        </button>
        <Link href="/profile" className="btn" style={{ fontSize: 13 }}>
          Profile
        </Link>
        <Link href="/dashboard" className="btn" style={{ fontSize: 13 }}>
          Twin
        </Link>
        <button className="btn" onClick={finishSession} disabled={ending || !sessionId} style={{ fontSize: 13 }}>
          {ending ? "Snapshotting…" : "End session"}
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => {
            clearUser();
            router.push("/");
          }}
          style={{ fontSize: 13 }}
        >
          Sign out
        </button>
      </header>

      {/* backend unreachable banner */}
      {apiError && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "10px 18px",
            background: "rgba(208,59,59,0.12)",
            borderBottom: "1px solid var(--critical)",
            fontSize: 13.5,
            flexShrink: 0,
          }}
        >
          <span style={{ color: "var(--critical)", fontWeight: 700 }}>Backend unreachable</span>
          <span style={{ color: "var(--ink-2)" }}>
            Start it with{" "}
            <code style={{ fontFamily: "var(--mono)", background: "var(--surface-3)", padding: "1px 6px", borderRadius: 4 }}>
              cd backend; .venv\Scripts\python run.py
            </code>
          </span>
          <button className="btn" onClick={() => user && connect(user, subject)} style={{ marginLeft: "auto", fontSize: 12.5, padding: "5px 12px" }}>
            Retry
          </button>
        </div>
      )}

      {/* 3 panes: nav | main conversation | workspace */}
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* left nav — topics & branches, always visible */}
        <nav
          style={{
            width: 240,
            flexShrink: 0,
            borderRight: "1px solid var(--border)",
            background: "var(--surface)",
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
          }}
        >
          <div style={{ padding: "12px 14px 6px", fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink-3)" }}>
            Topics
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "0 8px" }}>
            {sortedTopics.map((n) => (
              <button
                key={n.id}
                onClick={() => selectConceptById(n.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  width: "100%",
                  textAlign: "left",
                  padding: "7px 10px",
                  borderRadius: 8,
                  border: "none",
                  cursor: "pointer",
                  fontSize: 13,
                  background: selected?.id === n.id ? "var(--accent-dim)" : "transparent",
                  color: selected?.id === n.id ? "var(--accent-strong)" : "var(--ink-2)",
                }}
              >
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: masteryColor(n.mastery),
                    border: "1px solid var(--border-strong)",
                    flexShrink: 0,
                  }}
                />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {n.name}
                </span>
              </button>
            ))}
          </div>

          {/* branches of the open topic */}
          {selected && (
            <div style={{ borderTop: "1px solid var(--border)", maxHeight: "45%", display: "flex", flexDirection: "column" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px 6px" }}>
                <span style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--ink-3)" }}>
                  ⑂ Chats · {selected.name.slice(0, 14)}
                </span>
                <button
                  className="btn btn-ghost"
                  onClick={() => setNewChatOpen((o) => !o)}
                  title="Start a new chat under this topic"
                  style={{ padding: "0 8px", fontSize: 15, lineHeight: 1.4, color: "var(--accent-strong)" }}
                >
                  ＋
                </button>
              </div>
              {newChatOpen && (
                <div style={{ padding: "0 10px 8px" }}>
                  <input
                    className="input"
                    autoFocus
                    placeholder="Ask or learn something new…"
                    value={newChatText}
                    onChange={(e) => setNewChatText(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && void startNewChat()}
                    style={{ fontSize: 12.5, padding: "6px 10px" }}
                  />
                </div>
              )}
              <div style={{ overflowY: "auto", padding: "0 8px 10px" }}>
                <button
                  onClick={() => setMainView({ type: "lesson" })}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "6px 10px",
                    borderRadius: 8,
                    border: "none",
                    cursor: "pointer",
                    fontSize: 12.5,
                    fontWeight: 600,
                    background: mainView.type === "lesson" ? "var(--accent-dim)" : "transparent",
                    color: mainView.type === "lesson" ? "var(--accent-strong)" : "var(--ink-2)",
                  }}
                >
                  ⌂ Main lesson
                </button>
                {branchItems.length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--ink-3)", padding: "4px 10px" }}>
                    Use ⑂ on a lesson block, or ＋ for a fresh chat.
                  </div>
                )}
                {branchItems.map((item) => {
                  const active = mainView.type === "branch" && mainView.item.key === item.key;
                  return (
                    <div
                      key={item.key}
                      style={{ display: "flex", alignItems: "center", borderRadius: 8, background: active ? "var(--accent-dim)" : "transparent" }}
                    >
                      <button
                        onClick={() => setMainView({ type: "branch", item })}
                        title={item.branch!.question}
                        style={{
                          flex: 1,
                          minWidth: 0,
                          textAlign: "left",
                          padding: "6px 4px 6px 10px",
                          border: "none",
                          background: "transparent",
                          cursor: "pointer",
                          fontSize: 12.5,
                          color: active ? "var(--accent-strong)" : "var(--ink-2)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        ⑂ {item.branch!.question}
                      </button>
                      <button
                        onClick={() => void removeBranch(item)}
                        title="Delete this branch permanently"
                        style={{ border: "none", background: "transparent", cursor: "pointer", color: "var(--ink-3)", fontSize: 12, padding: "4px 8px", flexShrink: 0 }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--critical)")}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--ink-3)")}
                      >
                        🗑
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </nav>

        {/* main conversation */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", justifyContent: "center", background: "var(--page)" }}>
          <div style={{ width: "100%", maxWidth: 860, display: "flex", flexDirection: "column", minHeight: 0 }}>
            {sessionId &&
              (mainView.type === "branch" ? (
                <BranchMain
                  branch={mainView.item.branch!}
                  onBack={() => setMainView({ type: "lesson" })}
                />
              ) : (
                <LessonPanel
                  userId={user.id}
                  sessionId={sessionId}
                  subject={subject}
                  concept={selected}
                  onSpawnExtra={(extra) =>
                    setPanelItems((xs) => [
                      { ...extra, key: `${extra.kind}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}` },
                      ...xs,
                    ])
                  }
                  onGraphChanged={() => refreshGraph(user.id, subject)}
                  onSelectConcept={selectConceptById}
                  onSelectConceptByName={selectConceptByName}
                  onOpenMap={() => setShowMap(true)}
                  onBlocksReady={setFirstBlockId}
                />
              ))}
          </div>
        </div>

        {/* right workspace */}
        <aside
          style={{
            width: 400,
            flexShrink: 0,
            borderLeft: "1px solid var(--border)",
            background: "var(--surface)",
            minHeight: 0,
          }}
        >
          <SidePanel
            items={panelItems}
            hiddenKeys={hiddenKeys}
            onHide={(key) => setHiddenKeys((s) => new Set(s).add(key))}
            onRestore={(key) =>
              setHiddenKeys((s) => {
                const next = new Set(s);
                next.delete(key);
                return next;
              })
            }
            onBranchFromDiagram={(ctx) => void branchFromDiagram(ctx)}
            onRegenerateSim={(item) => void regenerateSim(item)}
            onMakeBranchMain={(item) => setMainView({ type: "branch", item })}
          />
        </aside>
      </div>

      {/* knowledge map overlay */}
      <AnimatePresence>
        {showMap && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(13,13,15,0.92)", backdropFilter: "blur(4px)", display: "flex", flexDirection: "column" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 18px", borderBottom: "1px solid var(--border)" }}>
              <span style={{ fontSize: 14, fontWeight: 700 }}>🗺 {subject} — knowledge map</span>
              <span style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                click a concept to open it
              </span>
              <div style={{ flex: 1 }} />
              <button
                className="btn"
                onClick={() => setFocusMode((f) => !f)}
                disabled={!selected}
                style={{
                  fontSize: 13,
                  background: focusMode ? "var(--accent-dim)" : undefined,
                  borderColor: focusMode ? "var(--accent)" : undefined,
                  color: focusMode ? "var(--accent-strong)" : undefined,
                }}
              >
                ◎ Focus
              </button>
              <button className="btn" onClick={() => setShowMap(false)} style={{ fontSize: 13 }}>
                ✕ Close
              </button>
            </div>
            <div style={{ flex: 1, position: "relative" }}>
              <KnowledgeCanvas
                nodes={nodes}
                edges={edges}
                selectedId={selected?.id ?? null}
                focusMode={focusMode}
                onSelect={(node) => void openConcept(node)}
              />
              {nodes.length === 0 && (
                <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--ink-3)" }}>
                  Loading your knowledge map…
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}
