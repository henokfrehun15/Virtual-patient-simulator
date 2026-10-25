import type { ReactNode } from "react";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="auth-page">
      <section className="auth-brand">
        <div className="auth-brand-inner">
          <span className="logo-mark logo-mark-lg" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none">
              <path d="M12 3v18M3 12h18" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" />
            </svg>
          </span>
          <h1>Virtual Patient Simulator</h1>
          <p>
            Turn your course material into AI patients. Interview them, examine them,
            order investigations, and get scored feedback on every encounter.
          </p>
          <ul className="auth-brand-points">
            <li>Grounded in your uploaded course PDFs</li>
            <li>Practice and test modes with hidden diagnoses</li>
            <li>Deterministic rubric scoring and progress tracking</li>
          </ul>
        </div>
      </section>
      <section className="auth-form-side">{children}</section>
    </main>
  );
}
