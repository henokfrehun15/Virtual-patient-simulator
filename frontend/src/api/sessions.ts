import { apiFetch } from "./client";

export type SessionMode = "practice" | "test";

export interface SessionMessage {
  id: string;
  role: string;
  content: string;
  turn_number: number;
  created_at: string;
}

export interface SessionDetail {
  id: string;
  mode: SessionMode;
  status: string;
  current_turn: number;
  turn_limit: number;
  time_limit_seconds: number;
  started_at: string;
  last_activity_at: string | null;
  ended_at: string | null;
  completed_reason: string | null;
  scenario: {
    id: string;
    title: string;
    difficulty: string;
    estimated_duration_minutes: number;
  };
  patient: {
    name: string | null;
    age: number | null;
    sex: string | null;
  };
  chief_complaint: string;
  diagnosis: string | null;
  messages: SessionMessage[];
}

export function startSession(
  scenarioId: string,
  mode: SessionMode,
  idempotencyKey: string
): Promise<SessionDetail> {
  return apiFetch<SessionDetail>("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify({
      scenario_id: scenarioId,
      mode,
      idempotency_key: idempotencyKey,
    }),
  });
}

export function getSession(sessionId: string): Promise<SessionDetail> {
  return apiFetch<SessionDetail>(`/api/v1/sessions/${sessionId}`);
}
