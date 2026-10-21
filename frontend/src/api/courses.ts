import { apiFetch } from "./client";

export interface Course {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface CoursePage {
  items: Course[];
  total: number;
  page: number;
  page_size: number;
}

export interface MaterialVersion {
  id: string;
  version: number;
  status: string;
  created_at: string;
}

export interface Material {
  id: string;
  course_id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  sha256: string;
  created_at: string;
  latest_version: MaterialVersion | null;
}

export interface MaterialPage {
  items: Material[];
  total: number;
  page: number;
  page_size: number;
}

export interface ExtractionJob {
  id: string;
  job_type: string;
  status: string;
  attempts: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface MaterialStatus {
  material: Material;
  versions: MaterialVersion[];
  jobs: ExtractionJob[];
}

export function listCourses(page = 1): Promise<CoursePage> {
  return apiFetch<CoursePage>(`/api/v1/courses?page=${page}`);
}

export function createCourse(name: string, description: string | null): Promise<Course> {
  return apiFetch<Course>("/api/v1/courses", {
    method: "POST",
    body: JSON.stringify({ name, description }),
  });
}

export function getCourse(courseId: string): Promise<Course> {
  return apiFetch<Course>(`/api/v1/courses/${courseId}`);
}

export function listMaterials(courseId: string): Promise<MaterialPage> {
  return apiFetch<MaterialPage>(`/api/v1/courses/${courseId}/materials`);
}

export function getMaterialStatus(materialId: string): Promise<MaterialStatus> {
  return apiFetch<MaterialStatus>(`/api/v1/materials/${materialId}/status`);
}

export function uploadMaterial(courseId: string, file: File): Promise<Material> {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<Material>(`/api/v1/courses/${courseId}/materials`, {
    method: "POST",
    body: form,
  });
}
