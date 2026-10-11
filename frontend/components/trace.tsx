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
          className={`badge border ${connected ? "border-emerald-300/30 bg-emerald-400/10 text-emerald-200" : "border-red-300/30 bg-red-400/10 text-red-200 motion-safe:animate-pulse-soft"}`}
          role="status"
        >
          {connected ? "connected" : "reconnecting…"}
        </span>
      </div>
      {!connected && (
        <p role="alert" className="alert-error mt-2">
          Stream disconnected — retrying with backoff (attempt {reconnects}). Last events replayed
          from audit on reconnect.
        </p>
      )}
      <ol className="console mt-2 max-h-80 space-y-1 overflow-y-auto" aria-live="polite">
        {events.map((e, i) => (
          <li key={i} className="console-row">
            <span className="text-slate-500">{e.ts}</span>{" "}
            <span className="font-semibold text-cyan-300">{e.step}</span>{" "}
            <span>{e.message}</span>
          </li>
        ))}
        {events.length === 0 && (
          <li className="faint">Waiting for first event (p95 target &lt; 2s)…</li>
        )}
      </ol>
      <div ref={bottomRef} />
    </section>
  );
}
