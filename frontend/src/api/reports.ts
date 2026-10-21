import { apiFetch } from "./client";

export interface RubricResult {
  category: string;
  question: string;
  status: string;
  weight: number;
  critical: boolean;
  quality_score: number | null;
}

export interface ReportDetail {
  session_id: string;
  mode: string;
  scenario_title: string;
  completed_at: string | null;
  overall_score: number | null;
  history_score: number | null;
  communication_score: number | null;
  reasoning_score: number | null;
  diagnosis_score: number | null;
  critical_misses: string[];
  strengths: string[];
  gaps: string[];
  narrative: string | null;
  recommended_focus: string | null;
  diagnosis: { guess: string; normalized_label: string | null; verdict: string } | null;
  rubric_results: RubricResult[];
}

export interface ProgressCategory {
  category: string;
  rolling_score: number | null;
  rolling_attempts: number;
  trend: string | null;
}

export interface ProgressDetail {
  categories: ProgressCategory[];
  diagnosis_accuracy: number | null;
  sessions_completed: number;
}

export interface HistoryItem {
  id: string;
  scenario_title: string;
  mode: string;
  overall_score: number | null;
  diagnosis_verdict: string | null;
  ended_at: string | null;
}

export interface HistoryPage {
  items: HistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export function getSessionReport(sessionId: string): Promise<ReportDetail> {
  return apiFetch<ReportDetail>(`/api/v1/sessions/${sessionId}/report`);
}

export function getProgress(): Promise<ProgressDetail> {
  return apiFetch<ProgressDetail>("/api/v1/users/me/progress");
}

export function getHistory(page = 1): Promise<HistoryPage> {
  return apiFetch<HistoryPage>(`/api/v1/users/me/history?page=${page}`);
}
