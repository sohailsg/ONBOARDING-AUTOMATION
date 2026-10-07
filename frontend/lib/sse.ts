"use client";

import { useEffect, useRef, useState } from "react";
import { streamUrl } from "./api";
import { useAppStore } from "./store";
import type { TraceEvent } from "./api.types";

/**
 * useTraceStream — SSE client for GET /cases/{id}/stream.
 * Exponential backoff reconnect + last-N replay is server-side
 * (audit replay on reconnect); client keeps a banner state.
 */
export function useTraceStream(caseId: string | null) {
  const pushTrace = useAppStore((s) => s.pushTrace);
  const clearTrace = useAppStore((s) => s.clearTrace);
  const [connected, setConnected] = useState(false);
  const [reconnects, setReconnects] = useState(0);
  const retryRef = useRef(0);

  useEffect(() => {
    if (!caseId) return;
    clearTrace();
    let es: EventSource | null = null;
    let closed = false;
    let timer: ReturnType<typeof setTimeout>;

    const connect = () => {
      es = new EventSource(streamUrl(caseId), { withCredentials: true });
      es.onopen = () => {
        setConnected(true);
        retryRef.current = 0;
      };
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data) as TraceEvent;
          pushTrace(data);
        } catch {
          pushTrace({ message: ev.data, ts: new Date().toISOString() });
        }
      };
      es.onerror = () => {
        es?.close();
        setConnected(false);
        if (closed) return;
        retryRef.current += 1;
        setReconnects((n) => n + 1);
        // Exponential backoff, capped at 15s
        const delay = Math.min(1000 * 2 ** retryRef.current, 15000);
        timer = setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      es?.close();
      setConnected(false);
    };
  }, [caseId, pushTrace, clearTrace]);

  return { connected, reconnects };
}
