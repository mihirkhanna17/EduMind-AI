"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { completeOnboarding, getQuestions, listSubjects } from "@/lib/api";
import { loadUser, saveSubject } from "@/lib/session";
import type { OnboardingQuestion } from "@/lib/types";

const LEARNING_STYLES = [
  "Intuition first, math later",
  "Theory first, examples after",
  "Real-world examples and analogies",
  "Diagrams and visualizations",
];
const TIME_OPTIONS = ["<30 min/day", "30-60 min/day", "1-2 hrs/day", "2+ hrs/day"];

type Step = "subject" | "questions" | "profile" | "seeding";

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("subject");
  const [subjects, setSubjects] = useState<string[]>([]);
  const [subject, setSubject] = useState("");
  const [customSubject, setCustomSubject] = useState("");
  const [questions, setQuestions] = useState<OnboardingQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({});
  const [style, setStyle] = useState(LEARNING_STYLES[0]);
  const [time, setTime] = useState(TIME_OPTIONS[1]);
  const [goal, setGoal] = useState("");
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loadUser()) {
      router.replace("/");
      return;
    }
    listSubjects().then((r) => setSubjects(r.subjects)).catch(() => setSubjects([]));
  }, [router]);

  async function pickSubject(chosen: string) {
    setSubject(chosen);
    setLoadingQuestions(true);
    setError(null);
    setStep("questions");
    try {
      // Library subject → instant. Unknown subject → the Dynamic Onboarding
      // Agent generates (and persists) its template — one model call, ever.
      const r = await getQuestions(chosen);
      setQuestions(r.questions);
    } catch (err) {
      setError((err as Error).message);
      setStep("subject");
    } finally {
      setLoadingQuestions(false);
    }
  }

  function toggleMulti(key: string, option: string) {
    setAnswers((prev) => {
      const cur = new Set((prev[key] as string[]) ?? []);
      if (cur.has(option)) cur.delete(option);
      else cur.add(option);
      return { ...prev, [key]: [...cur] };
    });
  }

  async function finish() {
    const user = loadUser()!;
    setStep("seeding");
    try {
      await completeOnboarding({
        user_id: user.id,
        subject,
        answers,
        goals: { main_goal: goal },
        time_constraints: { daily: time },
        learning_prefs: { style },
      });
      saveSubject(user.id, subject);
      router.push("/learn");
    } catch (err) {
      setError((err as Error).message);
      setStep("profile");
    }
  }

  const answeredAll = questions.every((q) => {
    const a = answers[q.key];
    return q.type === "multi_select" ? Array.isArray(a) && a.length > 0 : !!a;
  });

  return (
    <main style={{ minHeight: "100vh", display: "grid", placeItems: "start center", padding: "8vh 20px" }}>
      <div style={{ width: 640, maxWidth: "94vw" }}>
        <header style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--accent)" }}>
            Onboarding
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 12 }}>
            {(["subject", "questions", "profile"] as Step[]).map((s, i) => (
              <div
                key={s}
                style={{
                  height: 4,
                  flex: 1,
                  borderRadius: 2,
                  background:
                    ["subject", "questions", "profile", "seeding"].indexOf(step) >= i
                      ? "var(--accent)"
                      : "var(--surface-3)",
                  transition: "background 300ms ease",
                }}
              />
            ))}
          </div>
        </header>

        <AnimatePresence mode="wait">
          {step === "subject" && (
            <motion.section
              key="subject"
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25 }}
            >
              <h1 style={{ fontSize: 24, fontWeight: 650 }}>What do you want to learn?</h1>
              <p style={{ color: "var(--ink-2)" }}>
                Pick a subject — or type any subject at all, and Edumind will design a
                curriculum for it.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, margin: "18px 0" }}>
                {subjects.map((s) => (
                  <button key={s} className="card" onClick={() => pickSubject(s)}
                    style={{ padding: "18px 16px", textAlign: "left", cursor: "pointer", color: "var(--ink)", fontSize: 15, fontWeight: 600, transition: "border-color 140ms ease" }}
                    onMouseEnter={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
                    onMouseLeave={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
                  >
                    {s}
                    <div style={{ fontSize: 12.5, color: "var(--ink-3)", fontWeight: 400, marginTop: 3 }}>
                      Curated starter curriculum
                    </div>
                  </button>
                ))}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <input
                  className="input"
                  placeholder="Anything else — “Music Theory”, “Organic Chemistry”, “Linear Algebra”…"
                  value={customSubject}
                  onChange={(e) => setCustomSubject(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && customSubject.trim() && pickSubject(customSubject.trim())}
                />
                <button
                  className="btn btn-primary"
                  disabled={!customSubject.trim()}
                  onClick={() => pickSubject(customSubject.trim())}
                >
                  Go
                </button>
              </div>
              {error && <p style={{ color: "var(--critical)", fontSize: 13 }}>{error}</p>}
            </motion.section>
          )}

          {step === "questions" && (
            <motion.section
              key="questions"
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25 }}
            >
              <h1 style={{ fontSize: 24, fontWeight: 650 }}>{subject}</h1>
              {loadingQuestions ? (
                <p style={{ color: "var(--ink-2)" }}>
                  Designing your {subject} onboarding…{" "}
                  <span style={{ color: "var(--ink-3)" }}>(new subjects take a few seconds)</span>
                </p>
              ) : (
                <>
                  {questions.map((q) => (
                    <div key={q.key} className="card" style={{ padding: 18, marginTop: 14 }}>
                      <div style={{ fontWeight: 600, marginBottom: 10 }}>{q.text}</div>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                        {q.options.map((opt) => {
                          const selected =
                            q.type === "multi_select"
                              ? ((answers[q.key] as string[]) ?? []).includes(opt)
                              : answers[q.key] === opt;
                          return (
                            <button
                              key={opt}
                              onClick={() =>
                                q.type === "multi_select"
                                  ? toggleMulti(q.key, opt)
                                  : setAnswers((p) => ({ ...p, [q.key]: opt }))
                              }
                              className="chip"
                              style={{
                                cursor: "pointer",
                                border: "1px solid",
                                borderColor: selected ? "var(--accent)" : "transparent",
                                background: selected ? "var(--accent-dim)" : "var(--surface-3)",
                                color: selected ? "var(--accent-strong)" : "var(--ink-2)",
                                padding: "7px 14px",
                              }}
                            >
                              {opt}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }}>
                    <button className="btn btn-ghost" onClick={() => setStep("subject")}>← Back</button>
                    <button className="btn btn-primary" disabled={!answeredAll} onClick={() => setStep("profile")}>
                      Continue
                    </button>
                  </div>
                </>
              )}
            </motion.section>
          )}

          {step === "profile" && (
            <motion.section
              key="profile"
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25 }}
            >
              <h1 style={{ fontSize: 24, fontWeight: 650 }}>How should Edumind teach you?</h1>
              <div className="card" style={{ padding: 18, marginTop: 14 }}>
                <div style={{ fontWeight: 600, marginBottom: 10 }}>Explanation style</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {LEARNING_STYLES.map((s) => (
                    <button key={s} onClick={() => setStyle(s)} className="chip"
                      style={{ cursor: "pointer", border: "1px solid", borderColor: style === s ? "var(--accent)" : "transparent", background: style === s ? "var(--accent-dim)" : "var(--surface-3)", color: style === s ? "var(--accent-strong)" : "var(--ink-2)", padding: "7px 14px" }}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
              <div className="card" style={{ padding: 18, marginTop: 14 }}>
                <div style={{ fontWeight: 600, marginBottom: 10 }}>Time you can give</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {TIME_OPTIONS.map((t) => (
                    <button key={t} onClick={() => setTime(t)} className="chip"
                      style={{ cursor: "pointer", border: "1px solid", borderColor: time === t ? "var(--accent)" : "transparent", background: time === t ? "var(--accent-dim)" : "var(--surface-3)", color: time === t ? "var(--accent-strong)" : "var(--ink-2)", padding: "7px 14px" }}>
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div className="card" style={{ padding: 18, marginTop: 14 }}>
                <div style={{ fontWeight: 600, marginBottom: 10 }}>Your goal, in your own words</div>
                <input className="input" placeholder="e.g. crack my OS end-sem, understand recursion deeply…"
                  value={goal} onChange={(e) => setGoal(e.target.value)} />
              </div>
              {error && <p style={{ color: "var(--critical)", fontSize: 13 }}>{error}</p>}
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }}>
                <button className="btn btn-ghost" onClick={() => setStep("questions")}>← Back</button>
                <button className="btn btn-primary" onClick={finish}>Build my knowledge canvas →</button>
              </div>
            </motion.section>
          )}

          {step === "seeding" && (
            <motion.section key="seeding" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
              style={{ textAlign: "center", paddingTop: 60 }}>
              <motion.div
                animate={{ scale: [1, 1.15, 1] }}
                transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
                style={{ width: 56, height: 56, borderRadius: "50%", background: "var(--accent-dim)", border: "2px solid var(--accent)", margin: "0 auto 18px" }}
              />
              <h2 style={{ fontWeight: 600 }}>Seeding your {subject} concept graph…</h2>
              <p style={{ color: "var(--ink-2)" }}>Mapping concepts, prerequisites, and your starting point.</p>
            </motion.section>
          )}
        </AnimatePresence>
      </div>
    </main>
  );
}
