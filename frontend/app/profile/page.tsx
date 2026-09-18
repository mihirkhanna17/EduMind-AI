"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  addConcept,
  fetchGraph,
  generateRoadmap,
  getProfile,
  listSessions,
  updateProfile,
  uploadDocument,
  type ProfileData,
  type SessionInfo,
} from "@/lib/api";
import { loadSubject, loadUser, saveSubject } from "@/lib/session";
import type { GraphNode, User } from "@/lib/types";

const LEARNING_STYLES = [
  "Intuition first, math later",
  "Theory first, examples after",
  "Real-world examples and analogies",
  "Diagrams and visualizations",
];
const TIME_OPTIONS = ["<30 min/day", "30-60 min/day", "1-2 hrs/day", "2+ hrs/day"];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card" style={{ padding: 20, marginTop: 16 }}>
      <h2 style={{ fontSize: 15, fontWeight: 700, margin: "0 0 12px" }}>{title}</h2>
      {children}
    </section>
  );
}

export default function ProfilePage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [style, setStyle] = useState("");
  const [time, setTime] = useState("");
  const [goal, setGoal] = useState("");
  const [saved, setSaved] = useState(false);
  const [newTopic, setNewTopic] = useState("");
  const [topicPrereqs, setTopicPrereqs] = useState<number[]>([]);
  const [concepts, setConcepts] = useState<GraphNode[]>([]);
  const [topicMsg, setTopicMsg] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [materialBusy, setMaterialBusy] = useState<string | null>(null);
  const [materialMsg, setMaterialMsg] = useState<string | null>(null);
  const [activeSubject, setActiveSubject] = useState<string | null>(null);

  useEffect(() => {
    const u = loadUser();
    if (!u) return void router.replace("/");
    setUser(u);
    getProfile(u.id)
      .then((p) => {
        setProfile(p);
        setStyle(String(p.learning_prefs.style ?? LEARNING_STYLES[0]));
        setTime(String(p.time_constraints.daily ?? TIME_OPTIONS[1]));
        setGoal(String(p.goals.main_goal ?? ""));
      })
      .catch((e) => setApiError((e as Error).message));
    listSessions(u.id).then((r) => setSessions(r.sessions)).catch(() => {});
    const subj = loadSubject(u.id);
    setActiveSubject(subj);
    if (subj) fetchGraph(u.id, subj).then((g) => setConcepts(g.nodes)).catch(() => {});
  }, [router]);

  async function save() {
    if (!user) return;
    await updateProfile(user.id, {
      learning_prefs: { style },
      time_constraints: { daily: time },
      goals: { main_goal: goal },
    });
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  async function onMaterialUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !user || !activeSubject) return;
    setMaterialMsg(null);
    setMaterialBusy("Uploading & indexing…");
    try {
      const doc = await uploadDocument(user.id, file);
      setMaterialBusy("Reading it and drafting your roadmap…");
      const roadmap = await generateRoadmap(user.id, doc.document_id, activeSubject);
      setMaterialMsg(
        `✓ "${doc.filename}" indexed. Added ${roadmap.added_concepts.length} concepts to your ${activeSubject} canvas` +
          (roadmap.skipped_existing ? ` (${roadmap.skipped_existing} already there)` : "") +
          ". Lessons will now teach from this material."
      );
      fetchGraph(user.id, activeSubject).then((g) => setConcepts(g.nodes)).catch(() => {});
    } catch (err) {
      setMaterialMsg(`⚠ ${(err as Error).message}`);
    } finally {
      setMaterialBusy(null);
      e.target.value = "";
    }
  }

  async function submitTopic() {
    if (!user || !activeSubject || !newTopic.trim()) return;
    setTopicMsg(null);
    try {
      const r = await addConcept(user.id, activeSubject, newTopic.trim(), topicPrereqs);
      setTopicMsg(`✓ "${r.name}" added to your ${activeSubject} canvas`);
      setNewTopic("");
      setTopicPrereqs([]);
      fetchGraph(user.id, activeSubject).then((g) => setConcepts(g.nodes));
    } catch (e) {
      setTopicMsg(`⚠ ${(e as Error).message}`);
    }
  }

  if (apiError) {
    return (
      <main style={{ maxWidth: 860, margin: "0 auto", padding: "24px 20px" }}>
        <div className="card" style={{ padding: 28, textAlign: "center" }}>
          <div style={{ fontSize: 16, fontWeight: 650, color: "var(--critical)", marginBottom: 6 }}>
            Backend unreachable
          </div>
          <p style={{ color: "var(--ink-2)", fontSize: 14 }}>
            Start it with <code style={{ fontFamily: "var(--mono)" }}>cd backend; .venv\Scripts\python run.py</code>,
            then <button className="btn" onClick={() => location.reload()} style={{ fontSize: 13, padding: "4px 12px" }}>retry</button>
          </p>
        </div>
      </main>
    );
  }

  if (!user || !profile) return null;

  const chipStyle = (selected: boolean): React.CSSProperties => ({
    cursor: "pointer",
    border: "1px solid",
    borderColor: selected ? "var(--accent)" : "transparent",
    background: selected ? "var(--accent-dim)" : "var(--surface-3)",
    color: selected ? "var(--accent-strong)" : "var(--ink-2)",
    padding: "7px 14px",
  });

  return (
    <main style={{ maxWidth: 860, margin: "0 auto", padding: "24px 20px 80px" }}>
      <header style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--accent)" }}>
          Edumind
        </span>
        <h1 style={{ fontSize: 20, fontWeight: 650, margin: 0 }}>Profile</h1>
        <div style={{ flex: 1 }} />
        <Link href="/learn" className="btn" style={{ fontSize: 13 }}>← Back to canvas</Link>
      </header>
      <p style={{ color: "var(--ink-2)", margin: 0 }}>
        {profile.user.name} · {profile.user.email}
      </p>

      <Section title="Your subjects">
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
          {profile.subjects.map((s) => (
            <button
              key={s}
              className="chip"
              style={chipStyle(s === activeSubject)}
              title={s === activeSubject ? "Active subject" : "Switch to this subject"}
              onClick={() => {
                if (user) saveSubject(user.id, s);
                router.push("/learn");
              }}
            >
              {s === activeSubject ? "● " : ""}{s}
            </button>
          ))}
          <Link href="/onboarding" className="chip" style={{ ...chipStyle(false), textDecoration: "none" }}>
            + Add a subject
          </Link>
        </div>
        <p style={{ fontSize: 12.5, color: "var(--ink-3)", margin: 0 }}>
          Adding a subject runs onboarding for it — any subject at all; unknown ones get a
          generated curriculum.
        </p>
      </Section>

      {activeSubject && (
        <Section title={`Study material for ${activeSubject}`}>
          <p style={{ fontSize: 13.5, color: "var(--ink-2)", marginTop: 0 }}>
            Upload your syllabus, notes, or slides (PDF / PPTX). Edumind builds a roadmap of
            concepts from it and grounds every lesson in your own material.
          </p>
          <label className="btn btn-primary" style={{ cursor: "pointer" }}>
            {materialBusy ?? "Upload material → generate roadmap"}
            <input type="file" accept=".pdf,.pptx" hidden onChange={onMaterialUpload} disabled={!!materialBusy} />
          </label>
          {materialMsg && (
            <p style={{ fontSize: 13, marginTop: 10, color: materialMsg.startsWith("✓") ? "#0ca30c" : "var(--critical)" }}>
              {materialMsg}
            </p>
          )}
        </Section>
      )}

      {activeSubject && (
        <Section title={`Add a topic to ${activeSubject}`}>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <input
              className="input"
              placeholder='e.g. "B-Trees", "Kirchhoff’s Laws"…'
              value={newTopic}
              onChange={(e) => setNewTopic(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submitTopic()}
            />
            <button className="btn btn-primary" onClick={submitTopic} disabled={!newTopic.trim()}>
              Add
            </button>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 8 }}>
            Optional — mark what it builds on:
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {concepts.map((c) => {
              const on = topicPrereqs.includes(c.id);
              return (
                <button
                  key={c.id}
                  className="chip"
                  style={chipStyle(on)}
                  onClick={() =>
                    setTopicPrereqs((p) => (on ? p.filter((x) => x !== c.id) : [...p, c.id]))
                  }
                >
                  {c.name}
                </button>
              );
            })}
          </div>
          {topicMsg && <p style={{ fontSize: 13, marginTop: 10, color: topicMsg.startsWith("✓") ? "#0ca30c" : "var(--critical)" }}>{topicMsg}</p>}
        </Section>
      )}

      <Section title="How Edumind teaches you">
        <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 8 }}>Explanation style</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
          {LEARNING_STYLES.map((s) => (
            <button key={s} className="chip" style={chipStyle(style === s)} onClick={() => setStyle(s)}>
              {s}
            </button>
          ))}
        </div>
        <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 8 }}>Time you can give</div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
          {TIME_OPTIONS.map((t) => (
            <button key={t} className="chip" style={chipStyle(time === t)} onClick={() => setTime(t)}>
              {t}
            </button>
          ))}
        </div>
        <div style={{ fontWeight: 600, fontSize: 13.5, marginBottom: 8 }}>Goal</div>
        <input className="input" value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="Your current goal…" />
        <button className="btn btn-primary" onClick={save} style={{ marginTop: 14 }}>
          {saved ? "✓ Saved" : "Save preferences"}
        </button>
        <p style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 8 }}>
          Lessons, analogies, and simulations adapt to these immediately.
        </p>
      </Section>

      <Section title="Session history">
        {sessions.length === 0 ? (
          <p style={{ color: "var(--ink-2)", fontSize: 13.5, margin: 0 }}>No sessions yet.</p>
        ) : (
          sessions.map((s) => (
            <div key={s.session_id} style={{ display: "flex", gap: 12, padding: "8px 0", borderBottom: "1px solid var(--border)", fontSize: 13.5, alignItems: "baseline" }}>
              <span style={{ color: "var(--ink-3)", fontVariantNumeric: "tabular-nums" }}>#{s.session_id}</span>
              <span>{s.started_at ? new Date(s.started_at).toLocaleString() : "—"}</span>
              <span className="chip">{s.mode}</span>
              <span style={{ color: "var(--ink-3)" }}>{s.lesson_blocks} lesson blocks</span>
              <span style={{ marginLeft: "auto", color: s.ended_at ? "#0ca30c" : "var(--warning)" }}>
                {s.ended_at ? "completed" : "open"}
              </span>
            </div>
          ))
        )}
      </Section>
    </main>
  );
}
