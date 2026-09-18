"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import { answerAssessment, startAssessment } from "@/lib/api";
import type { GradeResult, QuizQuestion } from "@/lib/types";

interface Props {
  userId: number;
  subject: string;
  onFinished: () => void; // refresh the graph — confidence changed
  onTeach: (conceptName: string) => void; // jump straight into fixing a weak concept
}

interface ConceptResult {
  concept: string;
  scores: number[];
  misconceptions: string[];
}

export default function AssessmentPanel({ userId, subject, onFinished, onTeach }: Props) {
  const [assessmentId, setAssessmentId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [current, setCurrent] = useState(0);
  const [result, setResult] = useState<GradeResult | null>(null);
  const [shortAnswer, setShortAnswer] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [report, setReport] = useState<Map<string, ConceptResult>>(new Map());

  async function start() {
    setBusy(true);
    try {
      const r = await startAssessment(userId, subject);
      setAssessmentId(r.assessment_id);
      setQuestions(r.questions);
      setCurrent(0);
      setReport(new Map());
      setDone(false);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  async function answer(value: string) {
    if (!assessmentId || busy) return;
    setBusy(true);
    try {
      const r = await answerAssessment(assessmentId, questions[current].index, value);
      setResult(r);
      setReport((prev) => {
        const next = new Map(prev);
        const entry = next.get(r.concept) ?? { concept: r.concept, scores: [], misconceptions: [] };
        entry.scores.push(r.score);
        if (r.misconception) entry.misconceptions.push(r.misconception);
        next.set(r.concept, entry);
        return next;
      });
    } finally {
      setBusy(false);
    }
  }

  function next() {
    setResult(null);
    setShortAnswer("");
    if (current + 1 >= questions.length) {
      setDone(true);
      onFinished();
    } else {
      setCurrent((c) => c + 1);
    }
  }

  /* ── report view ── */
  if (done) {
    const rows = [...report.values()].map((r) => ({
      ...r,
      avg: r.scores.reduce((a, b) => a + b, 0) / r.scores.length,
    }));
    const overall = rows.length
      ? rows.reduce((a, r) => a + r.avg, 0) / rows.length
      : 0;
    const weak = rows.filter((r) => r.avg < 0.7).sort((a, b) => a.avg - b.avg);
    const strong = rows.filter((r) => r.avg >= 0.7);

    return (
      <div className="card" style={{ padding: 18 }}>
        <div style={{ fontWeight: 650, marginBottom: 4 }}>Diagnostic report</div>
        <div style={{ fontSize: 28, fontWeight: 700, marginBottom: 12 }}>
          {Math.round(overall * 100)}%
          <span style={{ fontSize: 13, fontWeight: 400, color: "var(--ink-3)", marginLeft: 8 }}>
            overall · {questions.length} questions
          </span>
        </div>

        {rows.map((r) => (
          <div key={r.concept} style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 13.5, fontWeight: 600 }}>{r.concept}</span>
              <div style={{ flex: 1, height: 5, background: "var(--surface-3)", borderRadius: 3, overflow: "hidden" }}>
                <div style={{ width: `${r.avg * 100}%`, height: "100%", background: r.avg >= 0.7 ? "var(--mastery-4)" : r.avg >= 0.4 ? "var(--mastery-2)" : "var(--mastery-1)", borderRadius: 3 }} />
              </div>
              <span style={{ fontSize: 12.5, color: "var(--ink-3)", fontVariantNumeric: "tabular-nums", width: 36, textAlign: "right" }}>
                {Math.round(r.avg * 100)}%
              </span>
              {r.avg < 0.7 && (
                <button className="btn" onClick={() => onTeach(r.concept)} style={{ padding: "3px 10px", fontSize: 12 }}>
                  Fix this →
                </button>
              )}
            </div>
            {r.misconceptions.map((m, i) => (
              <div key={i} style={{ fontSize: 12.5, color: "var(--warning)", marginTop: 4 }}>
                ⚠ Why you missed it: <span style={{ color: "var(--ink-2)" }}>{m}</span>
              </div>
            ))}
          </div>
        ))}

        {weak.length > 0 ? (
          <button
            className="btn btn-primary"
            onClick={() => onTeach(weak[0].concept)}
            style={{ marginTop: 14, width: "100%", justifyContent: "center" }}
          >
            Start fixing the weakest: {weak[0].concept} →
          </button>
        ) : (
          <p style={{ fontSize: 13.5, color: "var(--ink-2)", marginTop: 12 }}>
            Solid across the board{strong.length ? " — your canvas just got brighter" : ""}. 🎉
          </p>
        )}
        <button className="btn btn-ghost" onClick={start} style={{ marginTop: 8, fontSize: 13 }}>
          Run another diagnostic
        </button>
      </div>
    );
  }

  if (!assessmentId) {
    return (
      <div className="card" style={{ padding: 18 }}>
        <div style={{ fontWeight: 650, marginBottom: 6 }}>Diagnostic assessment</div>
        <p style={{ color: "var(--ink-2)", fontSize: 13.5 }}>
          A short adaptive quiz that maps where you stand in {subject}. You get a full report at
          the end — including <i>why</i> you missed what you missed — and one-click fixes.
        </p>
        <button className="btn btn-primary" onClick={start} disabled={busy}>
          {busy ? "Preparing…" : "Start diagnostic"}
        </button>
      </div>
    );
  }

  const q = questions[current];
  return (
    <motion.div
      key={q.index}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card"
      style={{ padding: 18 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
        <span className="chip">{q.concept}</span>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>
          {current + 1} / {questions.length}
        </span>
      </div>
      <div style={{ fontWeight: 600, marginBottom: 14 }}>{q.question}</div>

      {!result ? (
        q.type === "mcq" ? (
          <div style={{ display: "grid", gap: 8 }}>
            {q.options.map((opt, i) => (
              <button
                key={i}
                className="btn"
                disabled={busy}
                onClick={() => answer(String(i))}
                style={{ justifyContent: "flex-start", textAlign: "left" }}
              >
                <span style={{ color: "var(--ink-3)", fontWeight: 700, marginRight: 4 }}>
                  {String.fromCharCode(65 + i)}
                </span>
                {opt}
              </button>
            ))}
          </div>
        ) : (
          <div>
            <textarea
              className="input"
              rows={3}
              placeholder="Answer in your own words…"
              value={shortAnswer}
              onChange={(e) => setShortAnswer(e.target.value)}
            />
            <button
              className="btn btn-primary"
              style={{ marginTop: 10 }}
              disabled={busy || !shortAnswer.trim()}
              onClick={() => answer(shortAnswer.trim())}
            >
              {busy ? "Grading…" : "Submit"}
            </button>
          </div>
        )
      ) : (
        <div>
          <div
            style={{
              padding: "10px 14px",
              borderRadius: 10,
              background:
                result.score >= 0.7
                  ? "rgba(12,163,12,0.12)"
                  : result.score > 0
                    ? "rgba(250,178,25,0.10)"
                    : "rgba(208,59,59,0.12)",
              border: `1px solid ${
                result.score >= 0.7 ? "var(--good)" : result.score > 0 ? "var(--warning)" : "var(--critical)"
              }`,
              fontSize: 13.5,
            }}
          >
            <b>{Math.round(result.score * 100)}%</b> — {result.feedback}
            {result.misconception && (
              <div style={{ marginTop: 6, color: "var(--warning)" }}>
                ⚠ Root cause: {result.misconception}
              </div>
            )}
          </div>
          <button className="btn btn-primary" style={{ marginTop: 12 }} onClick={next}>
            {current + 1 >= questions.length ? "See report" : "Next question"}
          </button>
        </div>
      )}
    </motion.div>
  );
}
