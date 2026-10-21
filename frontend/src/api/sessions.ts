import { apiFetch } from "./client";

export type SessionMode = "practice" | "test";

export interface SessionMessage {
  id: string;
  role: string;
  content: string;
  turn_number: number;
  created_at: string;
}

export interface SessionActionRequest {
  id: string;
  result: Record<string, unknown>;
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
  examination_requests: Array<SessionActionRequest & { exam_name: string }>;
  investigation_requests: Array<SessionActionRequest & { test_name: string }>;
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

export interface ActionResult {
  id: string;
  result: Record<string, unknown>;
  created_at: string;
}

export function requestExamination(
  sessionId: string,
  examName: string,
  idempotencyKey: string
): Promise<ActionResult & { exam_name: string }> {
  return apiFetch(`/api/v1/sessions/${sessionId}/examinations`, {
    method: "POST",
    body: JSON.stringify({ exam_name: examName, idempotency_key: idempotencyKey }),
  });
}

export function requestInvestigation(
  sessionId: string,
  testName: string,
  idempotencyKey: string
): Promise<ActionResult & { test_name: string }> {
  return apiFetch(`/api/v1/sessions/${sessionId}/investigations`, {
    method: "POST",
    body: JSON.stringify({ test_name: testName, idempotency_key: idempotencyKey }),
  });
}

export function submitDiagnosis(
  sessionId: string,
  guess: string,
  idempotencyKey: string
): Promise<{ id: string; guess: string; verdict: string | null; created_at: string }> {
  return apiFetch(`/api/v1/sessions/${sessionId}/diagnosis`, {
    method: "POST",
    body: JSON.stringify({ guess, idempotency_key: idempotencyKey }),
  });
}

export function completeSession(sessionId: string): Promise<SessionDetail> {
  return apiFetch<SessionDetail>(`/api/v1/sessions/${sessionId}/complete`, {
    method: "POST",
    body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
  });
}
