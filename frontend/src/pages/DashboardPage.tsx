import { Link } from "react-router-dom";

import { useAuth } from "../features/auth/AuthContext";

export function DashboardPage() {
  const { user, logout } = useAuth();

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
          <h2>Scenarios</h2>
          <p>Scenario generation and browsing arrive in Phase 5.</p>
        </div>
        <div className="card">
          <h2>Progress</h2>
          <p>Longitudinal progress tracking arrives in Phase 9.</p>
        </div>
      </section>
    </main>
  );
}
