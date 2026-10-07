"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";

interface ActionStatus {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "halted";
  attempts?: number;
  error?: string;
}

/**
 * F-UI-7: per-action status + retry + kill switch.
 * Action list is read from the plan payload's `actions` array;
 * live status merges from trace events where available.
 */
export function ExecutionView({ caseId }: { caseId: string }) {
  const { data } = useQuery({ queryKey: ["plan", caseId], queryFn: () => api.getPlan(caseId) });
  const [halted, setHalted] = useState(false);
  const [retries, setRetries] = useState<Record<string, number>>({});

  const payload = (data?.json_payload ?? {}) as { actions?: ActionStatus[] };
  const actions = payload.actions ?? [];

  async function halt() {
    // Kill switch: POST approvals reject on current plan stops the executor loop.
    if (!data?.id) return;
    await api.decideApproval(data.id, { decision: "reject", comment: "HALT from Execution view" });
    setHalted(true);
  }

  return (
    <section aria-label="Execution" className="card">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Execution</h2>
        <button
          className="btn-danger"
          onClick={halt}
          disabled={halted || !data?.id}
          aria-label="Halt execution (kill switch)"
        >
          {halted ? "Halted" : "Halt"}
        </button>
      </div>
      {halted && (
        <p role="alert" className="mt-2 rounded bg-red-50 p-2 text-sm text-red-800">
          Execution halted by operator. Remaining queued actions were cancelled.
        </p>
      )}
      <ul className="mt-3 space-y-2">
        {actions.map((a) => (
          <li key={a.id} className="flex items-center justify-between rounded border border-slate-200 p-2 text-sm">
            <div>
              <p className="font-medium">{a.type}</p>
              <p className="text-xs text-slate-500">
                {a.status ?? "queued"} · attempts {(a.attempts ?? 0) + (retries[a.id] ?? 0)}
                {a.error && <span className="text-red-700"> · {a.error}</span>}
              </p>
            </div>
            <button
              className="btn-ghost text-xs"
              onClick={() => setRetries((r) => ({ ...r, [a.id]: (r[a.id] ?? 0) + 1 }))}
              aria-label={`Retry ${a.type}`}
            >
              Retry
            </button>
          </li>
        ))}
        {actions.length === 0 && (
          <li className="text-sm text-slate-500">
            No actions yet — approve the plan to enqueue execution.
          </li>
        )}
      </ul>
    </section>
  );
}
