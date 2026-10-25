import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getSessionReport, type RubricResult } from "../api/reports";

const STATUS_LABELS: Record<string, string> = {
  satisfied: "Satisfied",
  partially_satisfied: "Partial",
  attempted: "Attempted",
  poorly_asked: "Poorly asked",
  unsafe: "Unsafe",
  not_attempted: "Not attempted",
  not_applicable: "N/A",
};

function ScoreRing({ label, score }: { label: string; score: number | null }) {
  const value = score !== null ? Math.round(score) : null;
  const pct = value !== null ? Math.min(100, Math.max(0, value)) : 0;
  const radius = 34;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - pct / 100);
  const tone =
    value === null ? "ring-none" : value >= 75 ? "ring-good" : value >= 50 ? "ring-mid" : "ring-low";

  return (
    <div className={`score-card ${tone}`}>
      <div className="score-ring-wrap">
        <svg viewBox="0 0 80 80" className="score-ring" aria-hidden="true">
          <circle className="score-ring-track" cx="40" cy="40" r={radius} />
          <circle
            className="score-ring-fill"
            cx="40"
            cy="40"
            r={radius}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="score-value">{value !== null ? value : "—"}</div>
      </div>
      <div className="muted">{label}</div>
    </div>
  );
}

function RubricTable({ results }: { results: RubricResult[] }) {
  const grouped = new Map<string, RubricResult[]>();
  for (const result of results) {
    const group = grouped.get(result.category) ?? [];
    group.push(result);
    grouped.set(result.category, group);
  }

  return (
    <div className="rubric-groups">
      {[...grouped.entries()].map(([category, items]) => (
        <div key={category} className="rubric-group">
          <h4>{category.replace(/_/g, " ")}</h4>
          <ul>
            {items.map((item) => (
              <li
                key={`${item.category}-${item.question}`}
                className={item.critical ? "rubric-critical" : undefined}
              >
                <div className="rubric-question">
                  {item.question}
                  {item.critical && <span className="badge badge-critical">critical</span>}
                  <span
                    className={`badge ${
                      item.status === "satisfied"
                        ? "badge-published"
                        : item.status === "not_attempted"
                          ? "badge-failed"
                          : "badge-draft"
                    }`}
                  >
                    {STATUS_LABELS[item.status] ?? item.status}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function ReportPage() {
  const { sessionId } = useParams<{ sessionId: string }>();

  const reportQuery = useQuery({
    queryKey: ["reports", sessionId],
    queryFn: () => getSessionReport(sessionId!),
    enabled: sessionId !== undefined,
    retry: 1,
  });

  if (reportQuery.isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading report…</p>
      </main>
    );
  }
  if (reportQuery.isError || reportQuery.data === undefined) {
    return (
      <main className="page">
        <p className="error">Report not available yet.</p>
      </main>
    );
  }

  const report = reportQuery.data;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <nav className="breadcrumb">
            <Link to="/progress">Progress</Link>
            <span className="breadcrumb-sep">/</span>
            <span>Report</span>
          </nav>
          <h1>Encounter report</h1>
          <p className="muted">
            {report.scenario_title} · {report.mode} mode
            {report.completed_at !== null &&
              ` · completed ${new Date(report.completed_at).toLocaleString()}`}
          </p>
        </div>
      </header>

      <section className="score-row">
        <ScoreRing label="Overall" score={report.overall_score} />
        <ScoreRing label="History" score={report.history_score} />
        <ScoreRing label="Communication" score={report.communication_score} />
        <ScoreRing label="Reasoning" score={report.reasoning_score} />
        <ScoreRing label="Diagnosis" score={report.diagnosis_score} />
      </section>

      {report.diagnosis !== null && (
        <section className="section-block">
          <h3>Diagnosis</h3>
          <p className="kv">
            <span>
              Your answer: <strong>{report.diagnosis.guess}</strong>
            </span>
            <span>
              Verdict:{" "}
              <strong className={`verdict-${report.diagnosis.verdict}`}>
                {report.diagnosis.verdict}
              </strong>
            </span>
          </p>
        </section>
      )}

      {report.critical_misses.length > 0 && (
        <section className="section-block critical-block">
          <h3>Critical omissions</h3>
          <ul>
            {report.critical_misses.map((miss) => (
              <li key={miss}>{miss}</li>
            ))}
          </ul>
        </section>
      )}

      {report.narrative !== null && (
        <section className="section-block">
          <h3>Feedback</h3>
          <p className="narrative">{report.narrative}</p>
          {report.recommended_focus !== null && report.recommended_focus !== "" && (
            <p className="kv">
              <span>
                Recommended focus: <strong>{report.recommended_focus}</strong>
              </span>
            </p>
          )}
        </section>
      )}

      {report.strengths.length > 0 && (
        <section className="section-block">
          <h3>Strengths</h3>
          <ul>
            {report.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {report.gaps.length > 0 && (
        <section className="section-block">
          <h3>Gaps</h3>
          <ul>
            {report.gaps.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="section-block">
        <h3>History-taking rubric</h3>
        {report.rubric_results.length === 0 ? (
          <p className="muted">No rubric items were scored for this encounter.</p>
        ) : (
          <RubricTable results={report.rubric_results} />
        )}
      </section>
    </main>
  );
}
