import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  completeSession,
  getSession,
  requestExamination,
  requestInvestigation,
  submitDiagnosis,
  type SessionDetail,
} from "../api/sessions";
import { useSessionStream } from "../hooks/useSessionStream";

function formatClock(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function MessageBubble({
  role,
  content,
  streaming = false,
}: {
  role: string;
  content: string;
  streaming?: boolean;
}) {
  const className = role === "doctor" ? "bubble bubble-doctor" : "bubble bubble-patient";
  return (
    <div className={`${className}${streaming ? " bubble-streaming" : ""}`}>{content}</div>
  );
}

function ActionPanel({
  title,
  placeholder,
  buttonText,
  onSubmit,
  pending,
  entries,
}: {
  title: string;
  placeholder: string;
  buttonText: string;
  onSubmit: (value: string) => void;
  pending: boolean;
  entries: Array<{ id: string; name: string; result: Record<string, unknown> }>;
}) {
  const [value, setValue] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed === "" || pending) return;
    setValue("");
    onSubmit(trimmed);
  };

  return (
    <div className="action-panel">
      <h3>{title}</h3>
      <form className="action-form" onSubmit={handleSubmit}>
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={placeholder}
          disabled={pending}
        />
        <button type="submit" disabled={pending || value.trim() === ""}>
          {pending ? "…" : buttonText}
        </button>
      </form>
      {entries.length > 0 && (
        <ul className="action-results">
          {entries.map((entry) => (
            <li key={entry.id}>
              <strong>{entry.name}</strong>
              <pre className="action-result-json">
                {JSON.stringify(entry.result, null, 2)}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const sessionQuery = useQuery({
    queryKey: ["sessions", sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: sessionId !== undefined,
    refetchInterval: (query) =>
      query.state.data?.status === "completing" ? 2000 : false,
  });
  const { sendMessage, streamingMessage, isStreaming, error } = useSessionStream(
    sessionId ?? ""
  );

  const [draft, setDraft] = useState("");
  const [dxGuess, setDxGuess] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [dxSubmitted, setDxSubmitted] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const session: SessionDetail | undefined = sessionQuery.data;
  const messageCount = session?.messages.length ?? 0;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messageCount, streamingMessage]);

  useEffect(() => {
    if (session?.status === "completed") {
      void queryClient.invalidateQueries({ queryKey: ["reports", sessionId] });
      navigate(`/sessions/${sessionId}/report`, { replace: true });
    }
  }, [session?.status, navigate, queryClient, sessionId]);

  const examMutation = useMutation({
    mutationFn: (examName: string) =>
      requestExamination(sessionId!, examName, crypto.randomUUID()),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["sessions", sessionId] });
    },
    onError: (err) =>
      setActionError(err instanceof Error ? err.message : "Request failed."),
  });

  const investigationMutation = useMutation({
    mutationFn: (testName: string) =>
      requestInvestigation(sessionId!, testName, crypto.randomUUID()),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["sessions", sessionId] });
    },
    onError: (err) =>
      setActionError(err instanceof Error ? err.message : "Request failed."),
  });

  const diagnosisMutation = useMutation({
    mutationFn: () => submitDiagnosis(sessionId!, dxGuess.trim(), crypto.randomUUID()),
    onSuccess: () => {
      setActionError(null);
      setDxGuess("");
      setDxSubmitted(true);
    },
    onError: (err) =>
      setActionError(err instanceof Error ? err.message : "Submission failed."),
  });

  const completeMutation = useMutation({
    mutationFn: () => completeSession(sessionId!),
    onSuccess: () => {
      setActionError(null);
      void queryClient.invalidateQueries({ queryKey: ["sessions", sessionId] });
    },
    onError: (err) =>
      setActionError(err instanceof Error ? err.message : "Could not complete session."),
  });

  if (sessionQuery.isLoading) {
    return (
      <main className="page">
        <p className="muted">Loading…</p>
      </main>
    );
  }
  if (sessionQuery.isError || session === undefined) {
    return (
      <main className="page">
        <p className="error">Session not found.</p>
      </main>
    );
  }

  const remainingSeconds = Math.max(
    0,
    Math.floor(
      (new Date(session.started_at).getTime() + session.time_limit_seconds * 1000 - now) /
        1000
    )
  );
  const isActive = session.status === "active";

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (content === "" || isStreaming) return;
    setDraft("");
    void sendMessage(content, crypto.randomUUID());
  };

  const handleDiagnosis = (event: FormEvent) => {
    event.preventDefault();
    if (dxGuess.trim() === "" || diagnosisMutation.isPending) return;
    diagnosisMutation.mutate();
  };

  return (
    <main className="page session-page">
      <nav className="top-nav">
        <Link to="/">Dashboard</Link>
        <Link to="/courses">Courses</Link>
        <Link to={`/scenarios/${session.scenario.id}`}>{session.scenario.title}</Link>
      </nav>

      <header className="page-header">
        <div>
          <h1>{session.scenario.title}</h1>
          <p className="muted">
            {session.patient.name ?? "Patient"} · {session.patient.age ?? "—"} ·{" "}
            {session.patient.sex ?? "—"} · {session.chief_complaint}
          </p>
        </div>
        <div className="session-status">
          <span className={`badge badge-mode-${session.mode}`}>{session.mode}</span>
          <span className="timer">{formatClock(remainingSeconds)}</span>
          <span className="muted">
            turn {session.current_turn}/{session.turn_limit}
          </span>
          <span className={`badge ${isActive ? "badge-published" : "badge-draft"}`}>
            {session.status}
          </span>
        </div>
      </header>

      {session.mode === "practice" && session.diagnosis !== null && (
        <div className="diagnosis-banner">
          Practice target diagnosis: <strong>{session.diagnosis}</strong>
        </div>
      )}

      <section className="chat" aria-label="Conversation">
        {session.messages.length === 0 && streamingMessage === null && (
          <p className="muted chat-hint">
            Introduce yourself and ask an opening question, for example: "What brings you
            in today?"
          </p>
        )}
        {session.messages.map((message) => (
          <MessageBubble key={message.id} role={message.role} content={message.content} />
        ))}
        {streamingMessage !== null && (
          <MessageBubble role="patient" content={streamingMessage} streaming />
        )}
        <div ref={bottomRef} />
      </section>

      {error !== null && <div className="session-error">{error}</div>}
      {actionError !== null && <div className="session-error">{actionError}</div>}

      {isActive && (
        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Ask the patient a question…"
            disabled={isStreaming}
            rows={2}
          />
          <button type="submit" disabled={isStreaming || draft.trim() === ""}>
            {isStreaming ? "…" : "Send"}
          </button>
        </form>
      )}

      {isActive && (
        <section className="card">
          <h2>Clinical actions</h2>
          <div className="action-grid">
            <ActionPanel
              title="Physical examination"
              placeholder="e.g. respiratory examination"
              buttonText="Examine"
              onSubmit={(value) => examMutation.mutate(value)}
              pending={examMutation.isPending}
              entries={(session.examination_requests ?? []).map((request) => ({
                id: request.id,
                name: request.exam_name,
                result: request.result,
              }))}
            />
            <ActionPanel
              title="Investigations"
              placeholder="e.g. chest x-ray"
              buttonText="Order"
              onSubmit={(value) => investigationMutation.mutate(value)}
              pending={investigationMutation.isPending}
              entries={(session.investigation_requests ?? []).map((request) => ({
                id: request.id,
                name: request.test_name,
                result: request.result,
              }))}
            />
          </div>

          <form className="diagnosis-form" onSubmit={handleDiagnosis}>
            <h3>Final diagnosis</h3>
            <div className="action-form">
              <input
                value={dxGuess}
                onChange={(event) => setDxGuess(event.target.value)}
                placeholder="Your diagnosis…"
                disabled={diagnosisMutation.isPending}
              />
              <button
                type="submit"
                disabled={diagnosisMutation.isPending || dxGuess.trim() === ""}
              >
                {diagnosisMutation.isPending ? "…" : "Submit"}
              </button>
            </div>
            {dxSubmitted && (
              <p className="muted">
                Diagnosis submitted.{" "}
                {session.mode === "test"
                  ? "The result is revealed in your report after you complete the session."
                  : ""}
              </p>
            )}
          </form>

          <div className="complete-row">
            <button
              className="btn-complete"
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending}
            >
              {completeMutation.isPending || session.status === "completing"
                ? "Completing…"
                : "Complete session"}
            </button>
            <span className="muted">
              Scoring and your report are generated after completion.
            </span>
          </div>
        </section>
      )}
    </main>
  );
}
