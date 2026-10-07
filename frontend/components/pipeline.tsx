"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { api } from "@/lib/api";
import type { CaseStatus } from "@/lib/api.types";

const STATUSES: (CaseStatus | "")[] = [
  "",
  "pending_ingestion",
  "agent_processing",
  "awaiting_hr_approval",
  "executing",
  "needs_attention",
  "active",
];

/** F-UI-4: pipeline table with ?status= filter parity. */
export function Pipeline() {
  const [status, setStatus] = useState<CaseStatus | "">("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["cases", status || "all"],
    queryFn: () => api.listCases(status || undefined),
  });

  return (
    <section aria-label="Hiring pipeline" className="card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Pipeline</h2>
        <label className="flex items-center gap-2 text-sm">
          Status
          <select
            aria-label="Filter by status"
            className="input w-auto"
            value={status}
            onChange={(e) => setStatus(e.target.value as CaseStatus | "")}
          >
            {STATUSES.map((s) => (
              <option key={s || "all"} value={s}>
                {s || "all"}
              </option>
            ))}
          </select>
        </label>
      </div>

      {isLoading && <p aria-busy="true" className="mt-3 text-sm">Loading cases…</p>}
      {isError && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          Failed to load. <button className="btn-ghost ml-2" onClick={() => refetch()}>Retry</button>
        </p>
      )}

      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead>
            <tr className="border-b text-slate-500">
              <th scope="col" className="py-2 pr-2">Case</th>
              <th scope="col" className="py-2 pr-2">Employee</th>
              <th scope="col" className="py-2 pr-2">Status</th>
              <th scope="col" className="py-2">Plan v</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((c) => (
              <tr key={c.id} className="border-b last:border-0 hover:bg-slate-50">
                <td className="py-2 pr-2">
                  <Link className="underline" href={`/admin/cases/${c.id}`}>
                    {c.id?.slice(0, 8)}…
                  </Link>
                </td>
                <td className="py-2 pr-2">{c.employee_id?.slice(0, 8)}…</td>
                <td className="py-2 pr-2">
                  <span className="badge bg-slate-100 text-slate-700">{c.status}</span>
                </td>
                <td className="py-2">v{c.current_plan_version ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {data && data.items.length === 0 && (
          <p className="mt-2 text-sm text-slate-500">No cases with this status.</p>
        )}
      </div>
    </section>
  );
}
