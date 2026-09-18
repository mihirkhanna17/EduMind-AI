"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { login, signup } from "@/lib/api";
import { loadSubject, loadUser, saveUser } from "@/lib/session";

export default function AuthPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "signup">("signup");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const existing = loadUser();
    if (existing) router.replace(loadSubject(existing.id) ? "/learn" : "/onboarding");
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user =
        mode === "signup"
          ? await signup(email, name, password)
          : await login(email, password);
      saveUser(user);
      router.push(loadSubject(user.id) ? "/learn" : "/onboarding");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background:
          "radial-gradient(1000px 600px at 70% -10%, rgba(144,133,233,0.14), transparent), radial-gradient(800px 500px at 10% 110%, rgba(57,135,229,0.10), transparent)",
      }}
    >
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        style={{ width: 420, maxWidth: "92vw" }}
      >
        <div style={{ marginBottom: 28 }}>
          <div
            style={{
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--accent)",
              marginBottom: 10,
            }}
          >
            Edumind
          </div>
          <h1 style={{ fontSize: 30, lineHeight: 1.2, margin: 0, fontWeight: 650 }}>
            A tutor that learns
            <br />
            how <em style={{ color: "var(--accent-strong)", fontStyle: "normal" }}>you</em> learn.
          </h1>
          <p style={{ color: "var(--ink-2)", marginTop: 10 }}>
            Living knowledge canvas · misconception tracking · your digital learning twin.
          </p>
        </div>

        <form onSubmit={submit} className="card" style={{ padding: 24 }}>
          <div style={{ display: "flex", gap: 6, marginBottom: 18 }}>
            {(["signup", "login"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className="btn"
                style={{
                  flex: 1,
                  justifyContent: "center",
                  background: mode === m ? "var(--accent-dim)" : "transparent",
                  borderColor: mode === m ? "var(--accent)" : "var(--border)",
                  color: mode === m ? "var(--accent-strong)" : "var(--ink-2)",
                }}
              >
                {m === "signup" ? "Create account" : "Sign in"}
              </button>
            ))}
          </div>

          <label style={{ display: "block", marginBottom: 12 }}>
            <span style={{ fontSize: 13, color: "var(--ink-2)" }}>Email</span>
            <input
              className="input"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{ marginTop: 5 }}
            />
          </label>
          {mode === "signup" && (
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ fontSize: 13, color: "var(--ink-2)" }}>Name</span>
              <input
                className="input"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                style={{ marginTop: 5 }}
              />
            </label>
          )}
          <label style={{ display: "block", marginBottom: 18 }}>
            <span style={{ fontSize: 13, color: "var(--ink-2)" }}>Password</span>
            <input
              className="input"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{ marginTop: 5 }}
            />
          </label>

          {error && (
            <div style={{ color: "var(--critical)", fontSize: 13, marginBottom: 12 }}>{error}</div>
          )}

          <button className="btn btn-primary" disabled={busy} style={{ width: "100%", justifyContent: "center" }}>
            {busy ? "…" : mode === "signup" ? "Start learning" : "Continue"}
          </button>
        </form>
      </motion.div>
    </main>
  );
}
