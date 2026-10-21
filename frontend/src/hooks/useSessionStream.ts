import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { API_URL, getAccessToken } from "../api/client";

const RETRY_MESSAGE =
  "The patient is unable to respond right now. Please retry this turn.";

interface StreamEvent {
  text?: string;
  message?: string;
  code?: string;
}

export function useSessionStream(sessionId: string) {
  const queryClient = useQueryClient();
  const [streamingMessage, setStreamingMessage] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (content: string, idempotencyKey: string) => {
      setIsStreaming(true);
      setError(null);
      setStreamingMessage("");

      try {
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        const token = getAccessToken();
        if (token !== null) {
          headers.Authorization = `Bearer ${token}`;
        }

        const response = await fetch(
          `${API_URL}/api/v1/sessions/${sessionId}/messages/stream`,
          {
            method: "POST",
            headers,
            credentials: "include",
            body: JSON.stringify({ content, idempotency_key: idempotencyKey }),
          }
        );

        if (!response.ok || response.body === null) {
          let message = RETRY_MESSAGE;
          try {
            const body = (await response.json()) as { error?: { message?: string } };
            message = body.error?.message ?? message;
          } catch {
            // non-JSON error body
          }
          throw new Error(message);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finished = false;

        while (!finished) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          const frames = buffer.split("\n\n");
          buffer = frames.pop() ?? "";

          for (const frame of frames) {
            const lines = frame.split("\n");
            const eventLine = lines.find((line) => line.startsWith("event: "));
            const dataLine = lines.find((line) => line.startsWith("data: "));
            if (eventLine === undefined || dataLine === undefined) continue;

            const event = eventLine.slice("event: ".length);
            const payload = JSON.parse(dataLine.slice("data: ".length)) as StreamEvent;

            if (event === "token" && typeof payload.text === "string") {
              setStreamingMessage((previous) => (previous ?? "") + payload.text!);
            } else if (event === "done") {
              finished = true;
            } else if (event === "error") {
              setError(payload.message ?? RETRY_MESSAGE);
              finished = true;
            }
          }
        }

        await queryClient.invalidateQueries({ queryKey: ["sessions", sessionId] });
      } catch (err) {
        setError(err instanceof Error ? err.message : RETRY_MESSAGE);
      } finally {
        setIsStreaming(false);
        setStreamingMessage(null);
      }
    },
    [queryClient, sessionId]
  );

  return { sendMessage, streamingMessage, isStreaming, error };
}
