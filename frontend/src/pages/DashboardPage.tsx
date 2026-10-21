import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../features/auth/AuthContext";
import { getHistory } from "../api/reports";

export function DashboardPage() {
  const { user, logout } = useAuth();
  const historyQuery = useQuery({ queryKey: ["history"], queryFn: () => getHistory() });

  return (
    <main className="page">
      <header className="page-header">
        <h1>Virtual Patient Simulator</h1>
        <div>
          <span>{user?.full_name ?? user?.email}</span>
          <button onClick={() => void logout()}>Sign out</button>
        </div>
      </header>
      <section className="grid">
        <div className="card">
          <h2>Courses</h2>
          <p>Browse your courses and upload course PDFs for clinical content extraction.</p>
          <Link className="card-link" to="/courses">
            Open courses →
          </Link>
        </div>
        <div className="card">
          <h2>Progress</h2>
          <p>Category scores, diagnosis accuracy, and your session history.</p>
          <Link className="card-link" to="/progress">
            View progress →
          </Link>
        </div>
        <div className="card">
          <h2>AI provider settings</h2>
          <p>Add your Anthropic API key and model names to power the simulations.</p>
          <Link className="card-link" to="/settings">
            Open settings →
          </Link>
        </div>
      </section>

      <section className="card">
        <h2>Recent encounters</h2>
        {historyQuery.isLoading ? (
          <p className="muted">Loading…</p>
        ) : (historyQuery.data?.items.length ?? 0) === 0 ? (
          <p className="muted">
            No completed encounters yet. Pick a course, choose a scenario, and start
            practicing.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Mode</th>
                <th>Score</th>
                <th>Diagnosis</th>
              </tr>
            </thead>
            <tbody>
              {historyQuery.data?.items.slice(0, 5).map((item) => (
                <tr key={item.id}>
                  <td>
                    <Link to={`/sessions/${item.id}/report`}>{item.scenario_title}</Link>
                  </td>
                  <td>{item.mode}</td>
                  <td>{item.overall_score !== null ? Math.round(item.overall_score) : "—"}</td>
                  <td>{item.diagnosis_verdict ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}
