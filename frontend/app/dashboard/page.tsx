"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { getDue, getTwin, getTwinDiff, postReview, snapshotTwinNow } from "@/lib/api";
import { loadUser } from "@/lib/session";
import type { DueConcept, TwinDiff, TwinSnapshot, User } from "@/lib/types";

/* chart series colors — validated dark categorical slots 1+2 (adjacent pair) */
const MASTERY_COLOR = "#3987e5";
const CONFIDENCE_COLOR = "#008300";

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card" style={{ padding: "16px 18px", flex: 1, minWidth: 150 }}>
      <div style={{ fontSize: 12, color: "var(--ink-3)", fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{value}</div>
      {hint && <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 2 }}>{hint}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card" style={{ padding: 20, marginTop: 16 }}>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 12px" }}>{title}</h2>
      {children}
    </section>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [twin, setTwin] = useState<TwinSnapshot | null>(null);
  const [diff, setDiff] = useState<TwinDiff | null>(null);
  const [due, setDue] = useState<DueConcept[]>([]);
  const [noTwin, setNoTwin] = useState(false);
  const [apiDown, setApiDown] = useState(false);
  const [reviewed, setReviewed] = useState<Set<number>>(new Set());
  const [refreshing, setRefreshing] = useState(false);

  function loadAll(uid: number) {
    getTwin(uid)
      .then((t) => {
        setTwin(t);
        setNoTwin(false);
        setApiDown(false);
      })
      .catch((e) => {
        // a 404 means "no snapshot yet"; a network failure means the API is down
        if ((e as Error).message.toLowerCase().includes("fetch")) setApiDown(true);
        else setNoTwin(true);
      });
    getTwinDiff(uid).then(setDiff).catch(() => setDiff(null));
    getDue(uid).then((r) => setDue(r.due)).catch(() => setDue([]));
  }

  useEffect(() => {
    const u = loadUser();
    if (!u) return void router.replace("/");
    setUser(u);
    loadAll(u.id);
  }, [router]);

  async function refreshTwin() {
    if (!user || refreshing) return;
    setRefreshing(true);
    try {
      await snapshotTwinNow(user.id); // one batched summarize call
      loadAll(user.id);
    } finally {
      setRefreshing(false);
    }
  }

  const radarData = useMemo(() => {
    if (!twin) return [];
    const rows = Object.values(twin.knowledge_state);
    return rows
      .sort((a, b) => b.mastery + b.confidence - (a.mastery + a.confidence))
      .slice(0, 8)
      .map((r) => ({
        concept: r.name.length > 18 ? r.name.slice(0, 17) + "…" : r.name,
        mastery: Math.round(r.mastery * 100),
        confidence: Math.round(r.confidence * 100),
      }));
  }, [twin]);

  const avgMastery = useMemo(() => {
    if (!twin) return 0;
    const rows = Object.values(twin.knowledge_state);
    return rows.length ? rows.reduce((a, r) => a + r.mastery, 0) / rows.length : 0;
  }, [twin]);

  const unresolved = (twin?.misconception_ledger ?? []).filter((m) => !m.resolved);

  async function quickReview(conceptId: number, score: number) {
    if (!user) return;
    await postReview(user.id, conceptId, score);
    setReviewed((s) => new Set(s).add(conceptId));
  }

  if (!user) return null;

  return (
    <main style={{ maxWidth: 1060, margin: "0 auto", padding: "24px 20px 80px" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 20 }}>
        <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--accent)" }}>
          Edumind
        </span>
        <h1 style={{ fontSize: 20, fontWeight: 650, margin: 0 }}>Your digital twin</h1>
        {twin && <span className="chip">v{twin.version}</span>}
        <div style={{ flex: 1 }} />
        <button className="btn" onClick={refreshTwin} disabled={refreshing} style={{ fontSize: 13 }}>
          {refreshing ? "Snapshotting…" : "⟳ Update twin now"}
        </button>
        <Link href="/profile" className="btn" style={{ fontSize: 13 }}>Profile</Link>
        <Link href="/learn" className="btn" style={{ fontSize: 13 }}>← Back to canvas</Link>
      </header>

      {apiDown ? (
        <div className="card" style={{ padding: 32, textAlign: "center" }}>
          <div style={{ fontSize: 17, fontWeight: 650, color: "var(--critical)", marginBottom: 6 }}>
            Backend unreachable
          </div>
          <p style={{ color: "var(--ink-2)" }}>
            Start it with <code style={{ fontFamily: "var(--mono)" }}>cd backend; .venv\Scripts\python run.py</code>
          </p>
          <button className="btn btn-primary" onClick={() => user && loadAll(user.id)}>Retry</button>
        </div>
      ) : noTwin ? (
        <div className="card" style={{ padding: 32, textAlign: "center" }}>
          <div style={{ fontSize: 17, fontWeight: 650, marginBottom: 6 }}>No snapshot yet</div>
          <p style={{ color: "var(--ink-2)" }}>
            Your twin is built from your learning activity. Build the first snapshot now, or
            learn something and end a session.
          </p>
          <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
            <button className="btn btn-primary" onClick={refreshTwin} disabled={refreshing}>
              {refreshing ? "Building…" : "Build my twin now"}
            </button>
            <Link href="/learn" className="btn">Start learning</Link>
          </div>
        </div>
      ) : !twin ? (
        <div style={{ color: "var(--ink-3)" }}>Loading twin…</div>
      ) : (
        <>
          {/* stat row */}
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <StatTile label="Concepts tracked" value={String(Object.keys(twin.knowledge_state).length)} />
            <StatTile label="Avg mastery" value={`${Math.round(avgMastery * 100)}%`} />
            <StatTile
              label="Open misconceptions"
              value={String(unresolved.length)}
              hint={unresolved.length ? "address these first" : "clean slate"}
            />
            <StatTile label="Due for revision" value={String(due.length)} hint="spaced repetition" />
          </div>

          {/* knowledge radar */}
          <Section title="Knowledge state — strongest concepts">
            {radarData.length >= 3 ? (
              <div style={{ width: "100%", height: 340 }}>
                <ResponsiveContainer>
                  <RadarChart data={radarData} margin={{ top: 10, right: 40, bottom: 10, left: 40 }}>
                    <PolarGrid stroke="#2c2c2a" />
                    <PolarAngleAxis dataKey="concept" tick={{ fill: "#898781", fontSize: 12 }} />
                    <PolarRadiusAxis domain={[0, 100]} tick={{ fill: "#898781", fontSize: 10 }} axisLine={false} />
                    <Radar name="Mastery" dataKey="mastery" stroke={MASTERY_COLOR} fill={MASTERY_COLOR} fillOpacity={0.28} strokeWidth={2} />
                    <Radar name="Confidence" dataKey="confidence" stroke={CONFIDENCE_COLOR} fill={CONFIDENCE_COLOR} fillOpacity={0.18} strokeWidth={2} />
                    <Legend wrapperStyle={{ fontSize: 13, color: "var(--ink-2)" }} />
                    <Tooltip
                      contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border-strong)", borderRadius: 8, fontSize: 13 }}
                      labelStyle={{ color: "var(--ink)" }}
                      itemStyle={{ color: "var(--ink-2)" }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <p style={{ color: "var(--ink-2)", fontSize: 13.5 }}>
                Not enough assessed concepts yet — run the diagnostic to populate this.
              </p>
            )}
          </Section>

          {/* diff view */}
          <Section title={diff ? `How you've changed — v${diff.from_version} → v${diff.to_version}` : "How you've changed"}>
            {!diff ? (
              <p style={{ color: "var(--ink-2)", fontSize: 13.5 }}>
                Finish one more session and this becomes a before/after of your knowledge.
              </p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  {diff.concept_changes.length === 0 && (
                    <p style={{ color: "var(--ink-3)", fontSize: 13.5 }}>No measurable concept movement.</p>
                  )}
                  {diff.concept_changes.map((c, i) => (
                    <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid var(--border)", fontSize: 13.5 }}>
                      <span>{c.concept}</span>
                      {c.kind === "new" ? (
                        <span className="chip">new</span>
                      ) : (
                        <span style={{ color: c.kind === "improved" ? "#0ca30c" : "var(--serious)", fontWeight: 650, fontVariantNumeric: "tabular-nums" }}>
                          {c.kind === "improved" ? "▲" : "▼"}{" "}
                          {Math.abs(Math.round(((c.mastery_delta ?? 0) + (c.confidence_delta ?? 0)) * 50))}pt
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                <div>
                  {diff.new_misconceptions.map((m, i) => (
                    <div key={`n${i}`} style={{ fontSize: 13, color: "var(--warning)", marginBottom: 6 }}>
                      ⚠ New: <span style={{ color: "var(--ink-2)" }}>{m.text}</span>{" "}
                      <span style={{ color: "var(--ink-3)" }}>({m.concept})</span>
                    </div>
                  ))}
                  {diff.resolved_misconceptions.map((m, i) => (
                    <div key={`r${i}`} style={{ fontSize: 13, color: "#0ca30c", marginBottom: 6 }}>
                      ✓ Resolved: <span style={{ color: "var(--ink-2)" }}>{m.text}</span>
                    </div>
                  ))}
                  {diff.new_misconceptions.length === 0 && diff.resolved_misconceptions.length === 0 && (
                    <p style={{ color: "var(--ink-3)", fontSize: 13.5 }}>No misconception changes.</p>
                  )}
                </div>
              </div>
            )}
          </Section>

          {/* misconception ledger */}
          <Section title="Misconception ledger">
            {twin.misconception_ledger.length === 0 ? (
              <p style={{ color: "var(--ink-2)", fontSize: 13.5 }}>Nothing on record — keep answering questions so Edumind can catch wrong mental models early.</p>
            ) : (
              twin.misconception_ledger.map((m, i) => (
                <div key={i} style={{ display: "flex", gap: 10, alignItems: "baseline", padding: "8px 0", borderBottom: "1px solid var(--border)", fontSize: 13.5 }}>
                  <span style={{ color: m.resolved ? "#0ca30c" : "var(--warning)", fontWeight: 700, flexShrink: 0 }}>
                    {m.resolved ? "✓ resolved" : "⚠ open"}
                  </span>
                  <span style={{ color: "var(--ink-2)" }}>{m.text}</span>
                  <span className="chip" style={{ marginLeft: "auto", flexShrink: 0 }}>{m.concept}</span>
                </div>
              ))
            )}
          </Section>

          {/* cognitive + behavioral profile */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <Section title="Cognitive profile">
              <dl style={{ margin: 0, fontSize: 13.5 }}>
                <dt style={{ color: "var(--ink-3)", fontSize: 12 }}>Observed style</dt>
                <dd style={{ margin: "2px 0 10px", color: "var(--ink-2)" }}>{twin.cognitive_profile.observed_style ?? "—"}</dd>
                <dt style={{ color: "var(--ink-3)", fontSize: 12 }}>Pacing</dt>
                <dd style={{ margin: "2px 0 10px", color: "var(--ink-2)" }}>{twin.cognitive_profile.pacing ?? "—"}</dd>
                <dt style={{ color: "var(--ink-3)", fontSize: 12 }}>Strengths</dt>
                <dd style={{ margin: "2px 0 10px", color: "var(--ink-2)" }}>{(twin.cognitive_profile.strengths ?? []).join(" · ") || "—"}</dd>
                <dt style={{ color: "var(--ink-3)", fontSize: 12 }}>Gaps</dt>
                <dd style={{ margin: "2px 0 0", color: "var(--ink-2)" }}>{(twin.cognitive_profile.gaps ?? []).join(" · ") || "—"}</dd>
              </dl>
            </Section>
            <Section title="Behavior & next steps">
              <p style={{ fontSize: 13.5, color: "var(--ink-2)", marginTop: 0 }}>{twin.behavioral_profile.engagement ?? ""}</p>
              <p style={{ fontSize: 13.5, color: "var(--ink-2)" }}>{twin.behavioral_profile.question_asking ?? ""}</p>
              {(twin.behavioral_profile.recommendations ?? []).map((r, i) => (
                <div key={i} style={{ fontSize: 13.5, color: "var(--ink)", padding: "6px 10px", background: "var(--accent-dim)", borderRadius: 8, marginTop: 6 }}>
                  → {r}
                </div>
              ))}
            </Section>
          </div>

          {/* revision queue */}
          <Section title="Due for revision — spaced repetition">
            {due.length === 0 ? (
              <p style={{ color: "var(--ink-2)", fontSize: 13.5 }}>Nothing due. The scheduler will resurface concepts as retention decays.</p>
            ) : (
              due.map((d) => (
                <div key={d.concept_id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 0", borderBottom: "1px solid var(--border)", fontSize: 13.5 }}>
                  <span style={{ fontWeight: 600 }}>{d.name}</span>
                  <span style={{ color: "var(--ink-3)", fontSize: 12.5 }}>{d.overdue_days}d overdue</span>
                  <div style={{ flex: 1 }} />
                  {reviewed.has(d.concept_id) ? (
                    <span style={{ color: "#0ca30c", fontSize: 13 }}>✓ rescheduled</span>
                  ) : (
                    <>
                      <span style={{ fontSize: 12, color: "var(--ink-3)" }}>How well do you recall it?</span>
                      {[
                        { label: "Forgot", score: 0.1 },
                        { label: "Shaky", score: 0.5 },
                        { label: "Got it", score: 1.0 },
                      ].map((b) => (
                        <button key={b.label} className="btn" onClick={() => quickReview(d.concept_id, b.score)} style={{ padding: "4px 10px", fontSize: 12.5 }}>
                          {b.label}
                        </button>
                      ))}
                    </>
                  )}
                </div>
              ))
            )}
          </Section>
        </>
      )}
    </main>
  );
}
