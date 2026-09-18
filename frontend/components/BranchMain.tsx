"use client";

import { useEffect, useRef, useState } from "react";
import { branchHistory, continueBranch } from "@/lib/api";
import { mdToHtml } from "@/lib/markdown";
import type { BranchInfo } from "@/lib/types";

interface Props {
  branch: BranchInfo & { response?: string };
  onBack: () => void; // return to the lesson
}

/** A branch promoted to the main conversation — full-width thread with its
 * own input; the lesson is one click away and unchanged (separate thread). */
export default function BranchMain({ branch, onBack }: Props) {
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages([
      { role: "user", content: branch.question },
      ...(branch.response ? [{ role: "bot", content: branch.response }] : []),
    ]);
    branchHistory(branch.branch_id)
      .then((r) => {
        if (r.messages.length > 1) setMessages(r.messages);
      })
      .catch(() => {});
  }, [branch.branch_id, branch.question, branch.response]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

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
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "14px 18px 10px" }}>
        <button className="btn" onClick={onBack} style={{ fontSize: 13 }}>
          ← Lesson
        </button>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.09em", textTransform: "uppercase", color: "var(--accent-strong)" }}>
            ⑂ branch
          </div>
          <div style={{ fontSize: 14.5, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {branch.question}
          </div>
        </div>
      </div>

      <div ref={scroller} style={{ flex: 1, overflowY: "auto", padding: "8px 18px", display: "flex", flexDirection: "column", gap: 10 }}>
        {messages.map((m, i) => (
          <div
            key={i}
            className="markdown"
            style={{
              alignSelf: m.role === "user" ? "flex-end" : "flex-start",
              maxWidth: "86%",
              padding: "10px 14px",
              borderRadius: 12,
              fontSize: 14,
              background: m.role === "user" ? "var(--accent-dim)" : "var(--surface)",
              border: m.role === "user" ? "none" : "1px solid var(--border)",
              color: m.role === "user" ? "var(--accent-strong)" : "var(--ink-2)",
            }}
            dangerouslySetInnerHTML={{ __html: mdToHtml(m.content) }}
          />
        ))}
        {busy && <div style={{ fontSize: 13, color: "var(--ink-3)" }}>thinking…</div>}
      </div>

      <div style={{ display: "flex", gap: 8, padding: 14, borderTop: "1px solid var(--border)" }}>
        <input
          className="input"
          autoFocus
          placeholder="Continue this branch…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
        />
        <button className="btn btn-primary" onClick={send} disabled={busy || !input.trim()}>
          ↑
        </button>
      </div>
    </div>
  );
}
