"use client";

import type { User } from "./types";

const USER_KEY = "edumind.user";

export function saveUser(user: User) {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function loadUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as User) : null;
}

export function clearUser() {
  localStorage.removeItem(USER_KEY);
}

/* Subject is scoped PER USER — a fresh account must never inherit the
 * previous account's subject on this browser. */
const subjectKey = (userId: number) => `edumind.subject.${userId}`;

export function saveSubject(userId: number, subject: string) {
  localStorage.setItem(subjectKey(userId), subject);
}

export function loadSubject(userId: number): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(subjectKey(userId));
}

/** Mastery (0..1) → sequential ramp step. Magnitude, not judgment. */
export function masteryColor(mastery: number): string {
  const steps = [
    "var(--mastery-0)",
    "var(--mastery-1)",
    "var(--mastery-2)",
    "var(--mastery-3)",
    "var(--mastery-4)",
    "var(--mastery-5)",
  ];
  return steps[Math.min(5, Math.floor(mastery * 6))];
}
