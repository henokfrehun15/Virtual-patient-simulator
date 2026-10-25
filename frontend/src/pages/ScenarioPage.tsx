import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";

import { getScenario } from "../api/scenarios";
import { startSession, type SessionMode } from "../api/sessions";

export function ScenarioPage() {
  const { scenarioId } = useParams<{ scenarioId: string }>();
  const navigate = useNavigate();

  const scenarioQuery = useQuery({
    queryKey: ["scenarios", scenarioId],
    queryFn: () => getScenario(scenarioId!),
    enabled: scenarioId !== undefined,
  });

  const startMutation = useMutation({
    mutationFn: (mode: SessionMode) =>
      startSession(scenarioId!, mode, crypto.randomUUID()),
    onSuccess: (session) => navigate(`/sessions/${session.id}`),
  });

  if (scenarioQuery.isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (scenarioQuery.isError || scenarioQuery.data === undefined) {
    return (
      <main className="page">
        <p className="error">Scenario not found.</p>
      </main>
    );
  }

  const scenario = scenarioQuery.data;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <nav className="breadcrumb">
            <Link to={`/diseases/${scenario.disease.id}`}>{scenario.disease.name}</Link>
            <span className="breadcrumb-sep">/</span>
            <span>Scenario</span>
          </nav>
          <h1>{scenario.title}</h1>
          <p className="muted">Topic: {scenario.disease.name}</p>
        </div>
        <div className="disease-meta">
          <span className={`badge badge-difficulty-${scenario.difficulty}`}>
            {scenario.difficulty}
          </span>
          <span className="muted">≈ {scenario.estimated_duration_minutes} min</span>
        </div>
      </header>

      <section className="card">
        <h2>Patient</h2>
        <p className="kv">
          <span>
            <strong>{scenario.patient.name ?? "—"}</strong>
          </span>
          <span>{scenario.patient.age ?? "—"} years</span>
          <span>{scenario.patient.sex ?? "—"}</span>
        </p>
        <p className="muted">Presenting complaint: {scenario.chief_complaint}</p>
      </section>

      <section className="card">
        <h2>Start an encounter</h2>
        <div className="mode-buttons">
          <button
            className="btn-practice"
            onClick={() => startMutation.mutate("practice")}
            disabled={startMutation.isPending}
          >
            {startMutation.isPending && startMutation.variables === "practice"
              ? "Starting…"
              : "Practice mode"}
          </button>
          <button
            className="btn-test"
            onClick={() => startMutation.mutate("test")}
            disabled={startMutation.isPending}
          >
            {startMutation.isPending && startMutation.variables === "test"
              ? "Starting…"
              : "Test mode"}
          </button>
        </div>
        {startMutation.isError && (
          <p className="error">
            {startMutation.error instanceof Error
              ? startMutation.error.message
              : "Failed to start session."}
          </p>
        )}
        <p className="muted">
          Practice shows the diagnosis up front; test keeps it hidden until you submit
          your final answer.
        </p>
      </section>
    </main>
  );
}
