export interface User {
  id: number;
  email: string;
  name: string;
}

export interface OnboardingQuestion {
  key: string;
  text: string;
  type: "single_select" | "multi_select" | "free_text";
  options: string[];
}

export interface GraphNode {
  id: number;
  name: string;
  subject: string;
  confidence: number;
  mastery: number;
  misconceptions: { text: string; resolved?: boolean }[];
  last_reviewed: string | null;
}

export interface GraphEdge {
  source: number;
  target: number;
  kind: "parent" | "prerequisite";
}

export interface LessonBlock {
  id: number;
  type: string;
  content: string;
}

export interface QuizQuestion {
  index: number;
  concept: string;
  type: "mcq" | "short_answer";
  question: string;
  options: string[];
}

export interface GradeResult {
  score: number;
  feedback: string;
  misconception: string | null;
  concept: string;
  updated_confidence: number | null;
  answered: number;
  total: number;
}

export interface BranchInfo {
  branch_id: number;
  thread_id: string;
  question: string;
  response?: string;
}

export interface DiagramRegion {
  label: string;
  bbox: [number, number, number, number];
  description: string;
}

export interface Diagram {
  diagram_id: number;
  image_url: string;
  source: "upload" | "web" | "generated";
  regions: DiagramRegion[];
}

export interface Simulation {
  simulation_id: number;
  concept_id: number;
  library: string;
  code: string;
  cached: boolean;
}

export interface TwinSnapshot {
  version: number;
  snapshotted_at: string | null;
  cognitive_profile: {
    observed_style?: string;
    pacing?: string;
    strengths?: string[];
    gaps?: string[];
  };
  knowledge_state: Record<
    string,
    { name: string; subject: string; confidence: number; mastery: number; retention_score: number }
  >;
  misconception_ledger: { concept: string; text: string; resolved?: boolean; detected_at?: string }[];
  behavioral_profile: {
    engagement?: string;
    question_asking?: string;
    recommendations?: string[];
    last_session_activity?: Record<string, unknown>;
  };
}

export interface TwinDiff {
  from_version: number;
  to_version: number;
  from_date: string | null;
  to_date: string | null;
  concept_changes: {
    concept: string;
    kind: "new" | "improved" | "slipped";
    mastery?: number;
    mastery_delta?: number;
    confidence_delta?: number;
  }[];
  new_misconceptions: { concept: string; text: string }[];
  resolved_misconceptions: { concept: string; text: string }[];
}

export interface DueConcept {
  concept_id: number;
  name: string;
  subject: string;
  mastery: number;
  retention_score: number;
  due_at: string;
  overdue_days: number;
}
