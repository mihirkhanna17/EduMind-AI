import type {
  BranchInfo,
  Diagram,
  DueConcept,
  GradeResult,
  GraphEdge,
  GraphNode,
  LessonBlock,
  OnboardingQuestion,
  QuizQuestion,
  Simulation,
  TwinDiff,
  TwinSnapshot,
  User,
} from "./types";

export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

const post = <T,>(path: string, body: unknown) =>
  req<T>(path, { method: "POST", body: JSON.stringify(body) });

/* auth */
export const signup = (email: string, name: string, password: string) =>
  post<User>("/auth/signup", { email, name, password });
export const login = (email: string, password: string) =>
  post<User>("/auth/login", { email, password });

/* onboarding */
export const listSubjects = () => req<{ subjects: string[] }>("/onboarding/subjects");
export const getQuestions = (subject: string) =>
  req<{ subject: string; questions: OnboardingQuestion[] }>(
    `/onboarding/questions?subject=${encodeURIComponent(subject)}`
  );
export const completeOnboarding = (payload: {
  user_id: number;
  subject: string;
  answers: Record<string, unknown>;
  academic_profile?: Record<string, unknown>;
  goals?: Record<string, unknown>;
  time_constraints?: Record<string, unknown>;
  learning_prefs?: Record<string, unknown>;
}) =>
  post<{ subject: string; seeded_concepts: { id: number; name: string }[] }>(
    "/onboarding/complete",
    payload
  );

/* knowledge graph */
export const fetchGraph = (userId: number, subject: string) =>
  req<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
    `/graph?user_id=${userId}&subject=${encodeURIComponent(subject)}`
  );

/* sessions */
export const startSession = (userId: number, mode = "teach") =>
  post<{ session_id: number }>("/sessions/start", { user_id: userId, mode });
export const endSession = (sessionId: number) =>
  post<{ session_id: number; twin_version: number }>(`/sessions/${sessionId}/end`, {});

/* teaching — SSE stream via fetch reader */
export interface VisualSuggestion {
  image: boolean;
  image_query: string;
  simulation: boolean;
  sim_query: string;
}

export async function streamLesson(
  userId: number,
  sessionId: number,
  conceptId: number,
  onDelta: (text: string, replace: boolean) => void,
  onVisual?: (suggestion: VisualSuggestion) => void
): Promise<LessonBlock[]> {
  const res = await fetch(
    `${API}/teach/stream?user_id=${userId}&session_id=${sessionId}&concept_id=${conceptId}`
  );
  if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let blocks: LessonBlock[] = [];

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const raw of events) {
      const eventMatch = raw.match(/^event: (\w+)$/m);
      const dataMatch = raw.match(/^data: (.*)$/m);
      if (!eventMatch || !dataMatch) continue;
      const payload = JSON.parse(dataMatch[1]);
      if (eventMatch[1] === "delta") onDelta(payload.text, false);
      else if (eventMatch[1] === "replace") onDelta(payload.text, true);
      else if (eventMatch[1] === "done") blocks = payload.blocks;
      else if (eventMatch[1] === "visual" && onVisual) onVisual(payload as VisualSuggestion);
    }
  }
  return blocks;
}

/* chat (router-classified) */
export const chat = (payload: {
  user_id: number;
  session_id: number;
  message: string;
  concept_id?: number | null;
  thread_id?: string | null;
}) => post<{ mode: string; response: string }>("/chat", payload);

/* assessment */
export const startAssessment = (userId: number, subject: string) =>
  post<{ assessment_id: string; questions: QuizQuestion[] }>("/assessment/start", {
    user_id: userId,
    subject,
  });
export const answerAssessment = (assessmentId: string, index: number, answer: string) =>
  post<GradeResult>("/assessment/answer", {
    assessment_id: assessmentId,
    question_index: index,
    answer,
  });

/* branches */
export const openBranch = (payload: {
  user_id: number;
  session_id: number;
  parent_block_id?: number | null;
  concept_id?: number | null; // free-form "new chat" anchor
  question: string;
  parent_thread_id?: string;
}) => post<BranchInfo & { response: string }>("/branches", payload);
export const deleteBranch = (branchId: number) =>
  req<{ deleted: number }>(`/branches/${branchId}`, { method: "DELETE" });
export const continueBranch = (branchId: number, message: string) =>
  post<{ branch_id: number; response: string }>(`/branches/${branchId}/message`, { message });
export const branchHistory = (branchId: number) =>
  req<{ messages: { role: string; content: string }[] }>(`/branches/${branchId}/history`);

/* images */
export const fetchWebImage = (query: string, conceptId?: number | null) =>
  post<Diagram>("/images/fetch", { query, concept_id: conceptId ?? null });
export const generateDiagram = (description: string, conceptId?: number | null) =>
  post<Diagram>("/images/generate", { description, concept_id: conceptId ?? null });
export async function uploadImage(file: File, conceptId?: number | null): Promise<Diagram> {
  const form = new FormData();
  form.append("file", file);
  const qs = conceptId ? `?concept_id=${conceptId}` : "";
  const res = await fetch(`${API}/images/upload${qs}`, { method: "POST", body: form });
  if (!res.ok) throw new Error("upload failed");
  return res.json();
}
export const imagesForConcept = (conceptId: number) =>
  req<{ diagrams: Diagram[] }>(`/images/concept/${conceptId}`);
export const branchesForConcept = (conceptId: number, userId: number) =>
  req<{ branches: (BranchInfo & { response: string })[] }>(
    `/branches/concept/${conceptId}?user_id=${userId}`
  );
export const cachedSimulation = (userId: number, conceptId: number) =>
  req<({ found: true } & Simulation) | { found: false }>(
    `/simulations/cached?user_id=${userId}&concept_id=${conceptId}`
  );

/* study material */
export async function uploadDocument(userId: number, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/documents/upload?user_id=${userId}`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "upload failed");
  }
  return res.json() as Promise<{ document_id: number; filename: string }>;
}
export const generateRoadmap = (userId: number, documentId: number, subject: string) =>
  post<{ added_concepts: { id: number; name: string }[]; skipped_existing: number }>(
    "/documents/roadmap",
    { user_id: userId, document_id: documentId, subject }
  );
export const askRegion = (diagramId: number, regionLabel: string, question: string) =>
  post<{ answer: string }>(`/images/${diagramId}/ask`, {
    region_label: regionLabel,
    question,
  });
export const cropAsk = (diagramId: number, bbox: number[]) =>
  post<{ description: string; cached: boolean }>(`/images/${diagramId}/crop`, { bbox });

/* simulations */
export const getSimulation = (userId: number, conceptId: number, force = false) =>
  post<Simulation>("/simulations", { user_id: userId, concept_id: conceptId, force });

/* stored lessons + plan */
export const getStoredLesson = (userId: number, conceptId: number) =>
  req<{ blocks: LessonBlock[] }>(`/teach/lessons?user_id=${userId}&concept_id=${conceptId}`);
export interface PlanEntry {
  concept_id: number;
  name: string;
  mastery: number;
  status: "ready" | "locked" | "done";
  prerequisites: string[];
}
export const getPlan = (userId: number, subject: string) =>
  req<{ plan: PlanEntry[] }>(`/plan?user_id=${userId}&subject=${encodeURIComponent(subject)}`);
export const addConcept = (userId: number, subject: string, name: string, prerequisiteIds: number[] = []) =>
  post<{ id: number; name: string }>("/concepts", {
    user_id: userId,
    subject,
    name,
    prerequisite_ids: prerequisiteIds,
  });

/* profile + sessions */
export interface ProfileData {
  user: { id: number; email: string; name: string };
  subjects: string[];
  learning_prefs: Record<string, unknown>;
  goals: Record<string, unknown>;
  time_constraints: Record<string, unknown>;
}
export const getProfile = (userId: number) => req<ProfileData>(`/profile/${userId}`);
export const updateProfile = (
  userId: number,
  data: Partial<Pick<ProfileData, "learning_prefs" | "goals" | "time_constraints">>
) => req<{ ok: boolean }>(`/profile/${userId}`, { method: "PUT", body: JSON.stringify(data) });
export interface SessionInfo {
  session_id: number;
  mode: string;
  started_at: string | null;
  ended_at: string | null;
  lesson_blocks: number;
}
export const listSessions = (userId: number) =>
  req<{ sessions: SessionInfo[] }>(`/sessions?user_id=${userId}`);
export const snapshotTwinNow = (userId: number) =>
  post<{ version: number }>(`/twin/${userId}/snapshot`, {});

/* twin + revision */
export const getTwin = (userId: number) => req<TwinSnapshot>(`/twin/${userId}`);
export const getTwinDiff = (userId: number) => req<TwinDiff>(`/twin/${userId}/diff`);
export const getDue = (userId: number) => req<{ due: DueConcept[] }>(`/revision/due?user_id=${userId}`);
export const postReview = (userId: number, conceptId: number, score: number) =>
  post<{ mastery: number; next_due_at: string | null }>("/revision/review", {
    user_id: userId,
    concept_id: conceptId,
    score,
  });
