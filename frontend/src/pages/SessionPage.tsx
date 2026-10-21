import { FormEvent, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getSession, type SessionDetail } from "../api/sessions";
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
  const className =
    role === "doctor"
      ? "bubble bubble-doctor"
      : "bubble bubble-patient";
  return (
    <div className={`${className}${streaming ? " bubble-streaming" : ""}`}>{content}</div>
  );
}

export function SessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const sessionQuery = useQuery({
    queryKey: ["sessions", sessionId],
    queryFn: () => getSession(sessionId!),
    enabled: sessionId !== undefined,
  });
  const { sendMessage, streamingMessage, isStreaming, error } = useSessionStream(
    sessionId ?? ""
  );

  const [draft, setDraft] = useState("");
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

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const content = draft.trim();
    if (content === "" || isStreaming) return;
    setDraft("");
    void sendMessage(content, crypto.randomUUID());
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

      {session.mode === "test" && (
        <section className="card">
          <h2>Test mode actions</h2>
          <div className="mode-buttons">
            <button disabled>Request examination</button>
            <button disabled>Request investigation</button>
            <button disabled>Submit final diagnosis</button>
          </div>
          <p className="muted">
            Examinations and investigations arrive in Phase 7; diagnosis submission in
            Phase 8.
          </p>
        </section>
      )}
    </main>
  );
}
