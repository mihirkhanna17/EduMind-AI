"use client";

import { useRef, useState } from "react";
import { API, askRegion, cropAsk } from "@/lib/api";
import type { Diagram, DiagramRegion } from "@/lib/types";

interface Props {
  diagram: Diagram;
  /** open a branch that goes deeper on the selected region/crop */
  onBranch?: (context: string) => void;
}

/** Interactive diagram: pre-segmented regions answer from cache, crop mode
 * lets the student box any area, ask about it, and branch into it. */
export default function DiagramViewer({ diagram, onBranch }: Props) {
  const [active, setActive] = useState<DiagramRegion | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [answerLabel, setAnswerLabel] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [cropMode, setCropMode] = useState(false);
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);
  const imgRef = useRef<HTMLDivElement>(null);

  const src = diagram.image_url.startsWith("/media/") ? `${API}${diagram.image_url}` : diagram.image_url;

  function norm(e: React.MouseEvent) {
    const r = imgRef.current!.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    };
  }

  async function finishCrop() {
    if (!drag) return;
    const x = Math.min(drag.x0, drag.x1);
    const y = Math.min(drag.y0, drag.y1);
    const w = Math.abs(drag.x1 - drag.x0);
    const h = Math.abs(drag.y1 - drag.y0);
    setDrag(null);
    if (w < 0.03 || h < 0.03) return;
    setBusy(true);
    setActive(null);
    setAnswerLabel("cropped area");
    try {
      const r = await cropAsk(diagram.diagram_id, [x, y, w, h]);
      setAnswer(`${r.cached ? "⚡ " : ""}${r.description}`);
    } finally {
      setBusy(false);
      setCropMode(false);
    }
  }

  async function ask() {
    if (!active || !question.trim()) return;
    setBusy(true);
    try {
      const r = await askRegion(diagram.diagram_id, active.label, question.trim());
      setAnswer(r.answer);
      setQuestion("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div
        ref={imgRef}
        style={{ position: "relative", cursor: cropMode ? "crosshair" : "default", lineHeight: 0 }}
        onMouseDown={(e) => {
          if (cropMode || e.shiftKey) {
            e.preventDefault();
            const p = norm(e);
            setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y });
          }
        }}
        onMouseMove={(e) => drag && setDrag({ ...drag, x1: norm(e).x, y1: norm(e).y })}
        onMouseUp={finishCrop}
        onMouseLeave={() => drag && finishCrop()}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt="diagram" style={{ width: "100%", display: "block", borderRadius: 8 }} draggable={false} />
        <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
          {diagram.regions.map((r) => (
            <rect
              key={r.label}
              x={`${r.bbox[0] * 100}%`}
              y={`${r.bbox[1] * 100}%`}
              width={`${r.bbox[2] * 100}%`}
              height={`${r.bbox[3] * 100}%`}
              rx="4"
              fill={active?.label === r.label ? "rgba(144,133,233,0.25)" : "rgba(144,133,233,0.06)"}
              stroke={active?.label === r.label ? "var(--accent)" : "rgba(144,133,233,0.55)"}
              strokeWidth="1.5"
              style={{ cursor: "pointer", pointerEvents: cropMode ? "none" : "auto" }}
              onClick={() => {
                setActive(r);
                setAnswerLabel(r.label);
                setAnswer(r.description); /* cached — zero model calls */
              }}
            />
          ))}
          {drag && (
            <rect
              x={`${Math.min(drag.x0, drag.x1) * 100}%`}
              y={`${Math.min(drag.y0, drag.y1) * 100}%`}
              width={`${Math.abs(drag.x1 - drag.x0) * 100}%`}
              height={`${Math.abs(drag.y1 - drag.y0) * 100}%`}
              fill="rgba(57,135,229,0.18)"
              stroke="var(--cyan)"
              strokeDasharray="4 3"
            />
          )}
        </svg>
      </div>

      <div style={{ padding: "10px 2px 2px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <button
            className="btn"
            onClick={() => setCropMode((c) => !c)}
            style={{
              padding: "4px 12px",
              fontSize: 12.5,
              background: cropMode ? "var(--accent-dim)" : undefined,
              borderColor: cropMode ? "var(--accent)" : undefined,
              color: cropMode ? "var(--accent-strong)" : undefined,
            }}
          >
            ✂ {cropMode ? "Drag a box on the image…" : "Crop & ask"}
          </button>
          <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
            or click an outlined region
          </span>
        </div>

        {busy && <div style={{ fontSize: 13, color: "var(--ink-2)" }}>Looking…</div>}

        {answer && !busy && (
          <div className="card" style={{ padding: "10px 12px", background: "var(--surface-2)" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--accent-strong)", marginBottom: 4 }}>
              {answerLabel}
            </div>
            <div style={{ fontSize: 13, color: "var(--ink-2)", maxHeight: 140, overflowY: "auto" }}>
              {answer}
            </div>
            {onBranch && (
              <button
                className="btn"
                onClick={() => onBranch(`${answerLabel}: ${answer.replace(/^⚡ /, "")}`)}
                style={{ marginTop: 8, padding: "4px 12px", fontSize: 12.5 }}
              >
                ⑂ Go deeper on this
              </button>
            )}
          </div>
        )}

        {active && (
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <input
              className="input"
              placeholder={`Ask about ${active.label}…`}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && ask()}
              style={{ fontSize: 13, padding: "7px 10px" }}
            />
            <button className="btn btn-primary" onClick={ask} disabled={busy || !question.trim()} style={{ padding: "7px 12px" }}>
              Ask
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
