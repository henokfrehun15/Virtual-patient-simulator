import { apiFetch } from "./client";

export type LLMProvider = "anthropic" | "groq";

export interface LLMSettings {
  provider: LLMProvider;
  api_key_set: boolean;
  api_key_source: string | null;
  extraction_model: string;
  scenario_model: string;
  patient_model: string;
  scoring_model: string;
  feedback_model: string;
}

export interface LLMSettingsUpdate {
  provider?: LLMProvider;
  api_key?: string;
  clear_api_key?: boolean;
  extraction_model?: string;
  scenario_model?: string;
  patient_model?: string;
  scoring_model?: string;
  feedback_model?: string;
}

export interface ModelTestResult {
  model: string;
  ok: boolean;
  error: string | null;
}

export function getLLMSettings(): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/v1/users/me/llm-settings");
}

export function updateLLMSettings(update: LLMSettingsUpdate): Promise<LLMSettings> {
  return apiFetch<LLMSettings>("/api/v1/users/me/llm-settings", {
    method: "PUT",
    body: JSON.stringify(update),
  });
}

export function testLLMConnection(): Promise<{ results: ModelTestResult[] }> {
  return apiFetch<{ results: ModelTestResult[] }>("/api/v1/users/me/llm-settings/test", {
    method: "POST",
  });
}
