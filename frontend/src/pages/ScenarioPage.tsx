import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getScenario } from "../api/scenarios";

export function ScenarioPage() {
  const { scenarioId } = useParams<{ scenarioId: string }>();

  const scenarioQuery = useQuery({
    queryKey: ["scenarios", scenarioId],
    queryFn: () => getScenario(scenarioId!),
    enabled: scenarioId !== undefined,
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
      <nav className="top-nav">
        <Link to="/">Dashboard</Link>
        <Link to="/courses">Courses</Link>
        <Link to={`/diseases/${scenario.disease.id}`}>{scenario.disease.name}</Link>
      </nav>
      <header className="page-header">
        <div>
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
          <button disabled>Practice mode</button>
          <button disabled>Test mode</button>
        </div>
        <p className="muted">
          Practice shows the diagnosis up front; test keeps it hidden until you submit your
          final answer. Patient encounters arrive with the session engine (Phase 6).
        </p>
      </section>
    </main>
  );
}
