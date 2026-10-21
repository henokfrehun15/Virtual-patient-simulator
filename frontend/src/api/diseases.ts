import { apiFetch } from "./client";

export interface DiseaseVersionSummary {
  id: string;
  version: number;
  name: string;
  status: string;
  created_at: string;
}

export interface DiseaseSummary {
  id: string;
  canonical_name: string;
  latest_version: DiseaseVersionSummary | null;
}

export interface DiseasePage {
  items: DiseaseSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface RubricItem {
  id: string;
  category: string;
  question_text: string;
  rationale: string | null;
  weight: number;
  critical: boolean;
}

export interface Evidence {
  page_number: number | null;
  evidence_text: string;
}

export interface DiagnosisOption {
  id: string;
  label: string;
  match_type: string;
}

export interface Finding {
  name: string;
  frequency: string;
}

export interface Investigation {
  name: string;
  typical_result: string;
}

export interface DiseaseVersionDetail {
  id: string;
  version: number;
  name: string;
  status: string;
  aliases: string[] | null;
  demographics: {
    age_range: string | null;
    sex_bias: string | null;
    risk_factors: string[] | null;
  } | null;
  symptoms: Finding[] | null;
  exam_findings: Finding[] | null;
  investigations: Investigation[] | null;
  differentials: string[] | null;
  red_flags: string[] | null;
  source_summary: Record<string, unknown> | null;
  created_at: string;
  rubric_items: RubricItem[];
  evidence: Evidence[];
  diagnosis_options: DiagnosisOption[];
}

export interface DiseaseDetail {
  id: string;
  canonical_name: string;
  versions: DiseaseVersionSummary[];
  latest_version: DiseaseVersionDetail | null;
}

export function listCourseDiseases(courseId: string): Promise<DiseasePage> {
  return apiFetch<DiseasePage>(`/api/v1/courses/${courseId}/diseases`);
}

export function getDisease(diseaseId: string): Promise<DiseaseDetail> {
  return apiFetch<DiseaseDetail>(`/api/v1/diseases/${diseaseId}`);
}
