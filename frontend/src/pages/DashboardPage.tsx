import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../features/auth/AuthContext";
import { getHistory } from "../api/reports";

function greetingForNow(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

const CARDS = [
  {
    to: "/courses",
    title: "Courses",
    body: "Browse your courses and upload course PDFs for clinical content extraction.",
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V2H6.5A2.5 2.5 0 0 0 4 4.5v15z" />
        <path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />
      </svg>
    ),
  },
  {
    to: "/progress",
    title: "Progress",
    body: "Category scores, diagnosis accuracy, and your session history.",
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M3 3v18h18" />
        <path d="M7 14l4-4 3 3 5-6" />
      </svg>
    ),
  },
  {
    to: "/settings",
    title: "AI provider settings",
    body: "Add your Anthropic or Groq API key and model names to power the simulations.",
    icon: (
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />
      </svg>
    ),
  },
];

export function DashboardPage() {
  const { user } = useAuth();
  const historyQuery = useQuery({ queryKey: ["history"], queryFn: () => getHistory() });
  const completed = historyQuery.data?.items.length ?? 0;
  const firstName = (user?.full_name ?? user?.email ?? "Doctor").split(" ")[0];

  return (
    <main className="page">
      <section className="hero">
        <h1>
          {greetingForNow()}, <span className="hero-accent">{firstName}</span>
        </h1>
        <p className="muted">
          Interview AI patients, order examinations and investigations, submit your
          diagnosis, and get scored feedback grounded in your course material.
        </p>
        <div className="hero-stats">
          <div className="hero-stat">
            <span className="hero-stat-value">{completed}</span>
            <span className="muted">completed encounters</span>
          </div>
          <Link className="btn-hero" to="/courses">
            Start practicing
          </Link>
        </div>
      </section>

      <section className="grid">
        {CARDS.map((card) => (
          <Link key={card.to} to={card.to} className="card nav-card">
            <span className="nav-card-icon">{card.icon}</span>
            <h2>{card.title}</h2>
            <p>{card.body}</p>
            <span className="card-link">Open →</span>
          </Link>
        ))}
      </section>

      <section className="card">
        <h2>Recent encounters</h2>
        {historyQuery.isLoading ? (
          <p className="muted">Loading…</p>
        ) : completed === 0 ? (
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
                  <td>
                    <span className={`badge badge-mode-${item.mode}`}>{item.mode}</span>
                  </td>
                  <td>
                    {item.overall_score !== null ? (
                      <span className="table-score">{Math.round(item.overall_score)}</span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    {item.diagnosis_verdict !== null ? (
                      <span className={`verdict-${item.diagnosis_verdict}`}>
                        {item.diagnosis_verdict}
                      </span>
                    ) : (
                      "—"
                    )}
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
