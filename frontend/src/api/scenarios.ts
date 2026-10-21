import { apiFetch } from "./client";

export interface ScenarioSummary {
  id: string;
  difficulty: string;
  title: string;
  estimated_duration_minutes: number;
  status: string;
  created_at: string;
}

export interface ScenarioPage {
  items: ScenarioSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface ScenarioDetail extends ScenarioSummary {
  disease: {
    id: string;
    canonical_name: string;
    name: string;
  };
  disease_version: number;
  chief_complaint: string;
  patient: {
    name: string | null;
    age: number | null;
    sex: string | null;
  };
  modes: string[];
}

export function listDiseaseScenarios(diseaseId: string): Promise<ScenarioPage> {
  return apiFetch<ScenarioPage>(`/api/v1/diseases/${diseaseId}/scenarios`);
}

export function getScenario(scenarioId: string): Promise<ScenarioDetail> {
  return apiFetch<ScenarioDetail>(`/api/v1/scenarios/${scenarioId}`);
}
