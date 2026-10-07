"use client";

import { useEffect, useRef } from "react";
import { useAppStore } from "@/lib/store";
import { useTraceStream } from "@/lib/sse";

/** F-UI-6: SSE-driven trace feed with auto-scroll + reconnect banner. */
export function TraceMonitor({ caseId }: { caseId: string }) {
  const events = useAppStore((s) => s.traceEvents);
  const { connected, reconnects } = useTraceStream(caseId);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  return (
    <section aria-label="Live trace" className="card">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Live trace</h2>
        <span
          className={`badge ${connected ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}
          role="status"
        >
          {connected ? "connected" : "reconnecting…"}
        </span>
      </div>
      {!connected && (
        <p role="alert" className="mt-2 rounded bg-red-50 p-2 text-sm text-red-800">
          Stream disconnected — retrying with backoff (attempt {reconnects}). Last events replayed
          from audit on reconnect.
        </p>
      )}
      <ol className="mt-2 max-h-80 space-y-1 overflow-y-auto font-mono text-xs" aria-live="polite">
        {events.map((e, i) => (
          <li key={i} className="rounded bg-slate-50 px-2 py-1">
            <span className="text-slate-400">{e.ts}</span>{" "}
            <span className="font-semibold text-brand-700">{e.step}</span>{" "}
            <span>{e.message}</span>
          </li>
        ))}
        {events.length === 0 && (
          <li className="text-slate-500">Waiting for first event (p95 target &lt; 2s)…</li>
        )}
      </ol>
      <div ref={bottomRef} />
    </section>
  );
}
