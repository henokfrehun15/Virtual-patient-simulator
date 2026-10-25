import { ChangeEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getCourse, listMaterials, uploadMaterial } from "../api/courses";
import { listCourseDiseases } from "../api/diseases";

const BUSY_STATUSES = ["uploaded", "extracting"];

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function CoursePage() {
  const { courseId } = useParams<{ courseId: string }>();
  const queryClient = useQueryClient();
  const [uploadError, setUploadError] = useState<string | null>(null);

  const courseQuery = useQuery({
    queryKey: ["courses", courseId],
    queryFn: () => getCourse(courseId!),
    enabled: courseId !== undefined,
  });

  const materialsQuery = useQuery({
    queryKey: ["courses", courseId, "materials"],
    queryFn: () => listMaterials(courseId!),
    enabled: courseId !== undefined,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const busy = items.some(
        (material) =>
          material.latest_version !== null &&
          BUSY_STATUSES.includes(material.latest_version.status)
      );
      return busy ? 2000 : false;
    },
  });

  const diseasesQuery = useQuery({
    queryKey: ["courses", courseId, "diseases"],
    queryFn: () => listCourseDiseases(courseId!),
    enabled: courseId !== undefined,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      const processing = items.some(
        (disease) => disease.latest_version !== null && disease.latest_version.status === "draft"
      );
      return processing ? 3000 : false;
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadMaterial(courseId!, file),
    onSuccess: () => {
      setUploadError(null);
      void queryClient.invalidateQueries({ queryKey: ["courses", courseId, "materials"] });
    },
    onError: (err) => setUploadError(err instanceof Error ? err.message : "Upload failed."),
  });

  const handleFileSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file !== undefined) {
      uploadMutation.mutate(file);
    }
    event.target.value = "";
  };

  if (courseQuery.isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (courseQuery.isError || courseQuery.data === undefined) {
    return (
      <main className="page">
        <p className="error">Course not found.</p>
      </main>
    );
  }

  const course = courseQuery.data;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <nav className="breadcrumb">
            <Link to="/courses">Courses</Link>
            <span className="breadcrumb-sep">/</span>
            <span>{course.name}</span>
          </nav>
          <h1>{course.name}</h1>
          {course.description !== null && <p className="muted">{course.description}</p>}
        </div>
      </header>

      <section className="card upload-card">
        <h2>Upload course PDF</h2>
        <p className="muted">
          PDFs are parsed, OCR-processed when needed, and split into chunks for clinical
          content extraction.
        </p>
        <input
          type="file"
          accept="application/pdf,.pdf"
          onChange={handleFileSelected}
          disabled={uploadMutation.isPending}
        />
        {uploadMutation.isPending && <p className="muted">Uploading…</p>}
        {uploadError !== null && <p className="error">{uploadError}</p>}
      </section>

      <section className="card">
        <h2>Materials</h2>
        {materialsQuery.isLoading ? (
          <p className="muted">Loading…</p>
        ) : (materialsQuery.data?.items.length ?? 0) === 0 ? (
          <p className="muted">No materials uploaded yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>File</th>
                <th>Size</th>
                <th>Status</th>
                <th>Uploaded</th>
              </tr>
            </thead>
            <tbody>
              {materialsQuery.data?.items.map((material) => {
                const status = material.latest_version?.status ?? "uploaded";
                return (
                  <tr key={material.id}>
                    <td>{material.filename}</td>
                    <td>{formatSize(material.size_bytes)}</td>
                    <td>
                      <span className={`badge badge-${status}`}>{status}</span>
                    </td>
                    <td>{new Date(material.created_at).toLocaleString()}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
      <section className="card">
        <h2>Extracted diseases</h2>
        {diseasesQuery.isLoading ? (
          <p className="muted">Loading…</p>
        ) : (diseasesQuery.data?.items.length ?? 0) === 0 ? (
          <p className="muted">
            Diseases appear here once clinical content extraction completes for your materials.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Disease</th>
                <th>Status</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {diseasesQuery.data?.items.map((disease) => {
                const status = disease.latest_version?.status ?? "draft";
                return (
                  <tr key={disease.id}>
                    <td>
                      <Link to={`/diseases/${disease.id}`}>
                        {disease.latest_version?.name ?? disease.canonical_name}
                      </Link>
                    </td>
                    <td>
                      <span className={`badge badge-${status}`}>{status}</span>
                    </td>
                    <td>v{disease.latest_version?.version ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
