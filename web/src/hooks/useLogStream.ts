"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Return type for useLogStream.
 */
export interface LogStreamState {
  /** Full accumulated log text (or null if nothing received yet). */
  logs: string | null;
  /** Current status reported by the server. */
  status: string | null;
  /** True while the SSE connection is open and streaming. */
  isStreaming: boolean;
  /** Non-null if the connection encountered an error. */
  error: string | null;
}

/**
 * Reusable hook that connects to an SSE log-stream endpoint.
 *
 * The server is expected to emit two event types:
 * - `log`  — `{ logs: string, status: string }` (partial update)
 * - `done` — `{ logs: string, status: string }` (terminal, stream closes)
 *
 * @param streamUrl  Full URL to the SSE endpoint (or `null` to disable).
 * @param token      JWT bearer token to authenticate the request.
 */
export function useLogStream(
  streamUrl: string | null,
  token: string | null,
): LogStreamState {
  const [state, setState] = useState<LogStreamState>({
    logs: null,
    status: null,
    isStreaming: false,
    error: null,
  });

  // Keep a ref so we can close on unmount without depending on state.
  const esRef = useRef<EventSource | null>(null);

  const close = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  useEffect(() => {
    // If no URL provided, reset and bail.
    if (!streamUrl) {
      close();
      setState({ logs: null, status: null, isStreaming: false, error: null });
      return;
    }

    // EventSource doesn't support custom headers, so we pass the token
    // as a query parameter. The backend auth middleware accepts ?token=...
    const separator = streamUrl.includes("?") ? "&" : "?";
    const url = token ? `${streamUrl}${separator}token=${token}` : streamUrl;

    close(); // close any prior connection

    const es = new EventSource(url);
    esRef.current = es;

    setState((prev) => ({ ...prev, isStreaming: true, error: null }));

    function handleLog(event: MessageEvent) {
      try {
        const payload = JSON.parse(event.data) as {
          logs: string;
          status: string;
        };
        setState({
          logs: payload.logs,
          status: payload.status,
          isStreaming: true,
          error: null,
        });
      } catch {
        // Ignore malformed events.
      }
    }

    function handleDone(event: MessageEvent) {
      try {
        const payload = JSON.parse(event.data) as {
          logs: string;
          status: string;
        };
        setState({
          logs: payload.logs,
          status: payload.status,
          isStreaming: false,
          error: null,
        });
      } catch {
        // Ignore malformed events.
      }
      close();
    }

    function handleError() {
      // EventSource fires an error when the connection closes or fails.
      // If the readyState is CLOSED the server ended the stream (normal).
      if (es.readyState === EventSource.CLOSED) {
        setState((prev) => ({ ...prev, isStreaming: false }));
      } else {
        setState((prev) => ({
          ...prev,
          isStreaming: false,
          error: "Log stream connection lost",
        }));
      }
      close();
    }

    es.addEventListener("log", handleLog);
    es.addEventListener("done", handleDone);
    es.onerror = handleError;

    return () => {
      es.removeEventListener("log", handleLog);
      es.removeEventListener("done", handleDone);
      es.onerror = null;
      close();
    };
  }, [streamUrl, token, close]);

  return state;
}
