import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getHistory, getProgress } from "../api/reports";

const TREND_BADGES: Record<string, string> = {
  improving: "badge-published",
  stable: "badge-draft",
  declining: "badge-failed",
};

export function ProgressPage() {
  const progressQuery = useQuery({ queryKey: ["progress"], queryFn: getProgress });
  const historyQuery = useQuery({ queryKey: ["history"], queryFn: () => getHistory() });

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>Progress</h1>
          <p className="muted">
            Rolling scores over your last 10 completed encounters, per skill category.
          </p>
        </div>
      </header>

      <section className="section-block">
        <h3>Overview</h3>
        {progressQuery.isLoading ? (
          <p className="muted">Loading…</p>
        ) : progressQuery.data === undefined ||
          progressQuery.data.sessions_completed === 0 ? (
          <p className="muted">Complete an encounter to start tracking progress.</p>
        ) : (
          <div className="score-row">
            <div className="score-card">
              <div className="score-value">{progressQuery.data.sessions_completed}</div>
              <div className="muted">Completed sessions</div>
            </div>
            <div className="score-card">
              <div className="score-value">
                {progressQuery.data.diagnosis_accuracy !== null
                  ? `${Math.round(progressQuery.data.diagnosis_accuracy)}%`
                  : "—"}
              </div>
              <div className="muted">Diagnosis accuracy</div>
            </div>
          </div>
        )}
      </section>

      {progressQuery.data !== undefined && progressQuery.data.categories.length > 0 && (
        <section className="section-block">
          <h3>Skill categories</h3>
          <div className="progress-list">
            {progressQuery.data.categories.map((category) => (
              <div key={category.category} className="progress-row">
                <span className="progress-label">
                  {category.category.replace(/_/g, " ")}
                </span>
                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{
                      width: `${Math.min(100, category.rolling_score ?? 0)}%`,
                    }}
                  />
                </div>
                <span className="progress-value">
                  {category.rolling_score !== null
                    ? Math.round(category.rolling_score)
                    : "—"}
                </span>
                {category.trend !== null && (
                  <span className={`badge ${TREND_BADGES[category.trend] ?? "badge-draft"}`}>
                    {category.trend}
                  </span>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="section-block">
        <h3>Session history</h3>
        {historyQuery.isLoading ? (
          <p className="muted">Loading…</p>
        ) : (historyQuery.data?.items.length ?? 0) === 0 ? (
          <p className="muted">No completed sessions yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Mode</th>
                <th>Score</th>
                <th>Diagnosis</th>
                <th>Completed</th>
              </tr>
            </thead>
            <tbody>
              {historyQuery.data?.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link to={`/sessions/${item.id}/report`}>{item.scenario_title}</Link>
                  </td>
                  <td>{item.mode}</td>
                  <td>{item.overall_score !== null ? Math.round(item.overall_score) : "—"}</td>
                  <td>
                    {item.diagnosis_verdict !== null ? (
                      <span className={`verdict-${item.diagnosis_verdict}`}>
                        {item.diagnosis_verdict}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {item.ended_at !== null
                      ? new Date(item.ended_at).toLocaleString()
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
