import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import {
  getDisease,
  type DiseaseVersionDetail,
  type RubricItem,
} from "../api/diseases";

function Chips({ items }: { items: string[] }) {
  return (
    <div className="chips">
      {items.map((item) => (
        <span key={item} className="chip">
          {item}
        </span>
      ))}
    </div>
  );
}

function FindingList({ items }: { items: { name: string; frequency: string }[] }) {
  return (
    <div className="chips">
      {items.map((item) => (
        <span key={item.name} className="chip">
          {item.name}
          <span className="chip-note">{item.frequency}</span>
        </span>
      ))}
    </div>
  );
}

function RubricSection({ items }: { items: RubricItem[] }) {
  const grouped = new Map<string, RubricItem[]>();
  for (const item of items) {
    const group = grouped.get(item.category) ?? [];
    group.push(item);
    grouped.set(item.category, group);
  }

  return (
    <div className="rubric-groups">
      {[...grouped.entries()].map(([category, groupItems]) => (
        <div key={category} className="rubric-group">
          <h4>{category.replace(/_/g, " ")}</h4>
          <ul>
            {groupItems.map((item) => (
              <li key={item.id} className={item.critical ? "rubric-critical" : undefined}>
                <div className="rubric-question">
                  {item.question_text}
                  {item.critical && <span className="badge badge-critical">critical</span>}
                  <span className="chip-note">weight {item.weight}</span>
                </div>
                {item.rationale !== null && (
                  <div className="muted rubric-rationale">{item.rationale}</div>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function VersionDetail({ version }: { version: DiseaseVersionDetail }) {
  const demographics = version.demographics;
  return (
    <div className="disease-detail">
      <header className="disease-header">
        <div>
          <h2>{version.name}</h2>
          {(version.aliases ?? []).length > 0 && (
            <Chips items={version.aliases ?? []} />
          )}
        </div>
        <div className="disease-meta">
          <span className={`badge badge-${version.status}`}>{version.status}</span>
          <span className="muted">version {version.version}</span>
        </div>
      </header>

      <section className="section-block">
        <h3>Demographics</h3>
        {demographics === null ||
        (!demographics.age_range && !demographics.sex_bias && !(demographics.risk_factors ?? []).length) ? (
          <p className="muted">No demographic data in source.</p>
        ) : (
          <>
            <p className="kv">
              {demographics.age_range && <span>Age: {demographics.age_range}</span>}
              {demographics.sex_bias && <span>Sex: {demographics.sex_bias}</span>}
            </p>
            {(demographics.risk_factors ?? []).length > 0 && (
              <Chips items={demographics.risk_factors ?? []} />
            )}
          </>
        )}
      </section>

      <section className="section-block">
        <h3>Symptoms</h3>
        {(version.symptoms ?? []).length === 0 ? (
          <p className="muted">No symptoms extracted.</p>
        ) : (
          <FindingList items={version.symptoms ?? []} />
        )}
      </section>

      <section className="section-block">
        <h3>Examination findings</h3>
        {(version.exam_findings ?? []).length === 0 ? (
          <p className="muted">No examination findings extracted.</p>
        ) : (
          <FindingList items={version.exam_findings ?? []} />
        )}
      </section>

      <section className="section-block">
        <h3>Investigations</h3>
        {(version.investigations ?? []).length === 0 ? (
          <p className="muted">No investigations extracted.</p>
        ) : (
          <ul className="investigation-list">
            {(version.investigations ?? []).map((item) => (
              <li key={item.name}>
                <strong>{item.name}</strong>
                {item.typical_result && <span className="muted"> — {item.typical_result}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {(version.differentials ?? []).length > 0 && (
        <section className="section-block">
          <h3>Differentials</h3>
          <Chips items={version.differentials ?? []} />
        </section>
      )}

      {(version.red_flags ?? []).length > 0 && (
        <section className="section-block">
          <h3>Red flags</h3>
          <div className="chips">
            {(version.red_flags ?? []).map((flag) => (
              <span key={flag} className="chip chip-red">
                {flag}
              </span>
            ))}
          </div>
        </section>
      )}

      <section className="section-block">
        <h3>History-taking rubric</h3>
        {version.rubric_items.length === 0 ? (
          <p className="muted">No rubric items generated.</p>
        ) : (
          <RubricSection items={version.rubric_items} />
        )}
      </section>

      <section className="section-block">
        <h3>Accepted diagnosis answers</h3>
        <div className="chips">
          {version.diagnosis_options.map((option) => (
            <span key={option.id} className="chip">
              {option.label}
              <span className="chip-note">{option.match_type}</span>
            </span>
          ))}
        </div>
      </section>

      <section className="section-block">
        <h3>Source evidence</h3>
        {version.evidence.length === 0 ? (
          <p className="muted">No source evidence recorded.</p>
        ) : (
          <ul className="evidence-list">
            {version.evidence.map((item, index) => (
              <li key={index}>
                <span className="muted">
                  {item.page_number !== null ? `Page ${item.page_number}` : "Unknown page"}
                </span>
                <p className="evidence-text">{item.evidence_text}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export function DiseasePage() {
  const { diseaseId } = useParams<{ diseaseId: string }>();

  const diseaseQuery = useQuery({
    queryKey: ["diseases", diseaseId],
    queryFn: () => getDisease(diseaseId!),
    enabled: diseaseId !== undefined,
  });

  if (diseaseQuery.isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (diseaseQuery.isError || diseaseQuery.data === undefined) {
    return (
      <main className="page">
        <p className="error">Disease not found.</p>
      </main>
    );
  }

  const disease = diseaseQuery.data;

  return (
    <main className="page">
      <nav className="top-nav">
        <Link to="/">Dashboard</Link>
        <Link to="/courses">Courses</Link>
        <span>{disease.canonical_name}</span>
      </nav>
      <header className="page-header">
        <h1>{disease.canonical_name}</h1>
      </header>
      {disease.latest_version === null ? (
        <p className="muted">No extracted versions yet.</p>
      ) : (
        <VersionDetail version={disease.latest_version} />
      )}
    </main>
  );
}
