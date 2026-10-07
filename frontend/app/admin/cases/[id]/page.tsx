"use client";

import { useEffect, useState } from "react";
import { PlanEditor } from "@/components/plan-editor";
import { TraceMonitor } from "@/components/trace";
import { ExecutionView } from "@/components/execution";
import { useAppStore } from "@/lib/store";

type Tab = "plan" | "trace" | "execution";

export default function CaseDetailPage({ params }: { params: { id: string } }) {
  const [tab, setTab] = useState<Tab>("plan");
  const setSelected = useAppStore((s) => s.setSelectedCase);
  useEffect(() => {
    setSelected(params.id);
  }, [params.id, setSelected]);

  return (
    <main id="main" className="mx-auto max-w-6xl space-y-4 px-4 py-8">
      <h1 className="text-2xl font-bold">Case {params.id.slice(0, 8)}…</h1>
      <div role="tablist" aria-label="Case detail" className="flex gap-2">
        {(["plan", "trace", "execution"] as Tab[]).map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            className={tab === t ? "btn-primary" : "btn-ghost"}
            onClick={() => setTab(t)}
          >
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      {tab === "plan" && <PlanEditor caseId={params.id} />}
      {tab === "trace" && <TraceMonitor caseId={params.id} />}
      {tab === "execution" && <ExecutionView caseId={params.id} />}
    </main>
  );
}
