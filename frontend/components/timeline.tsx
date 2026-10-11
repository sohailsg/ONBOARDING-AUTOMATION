"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { progressOf } from "@/lib/utils";
import type { ChecklistItem } from "@/lib/api.types";

interface Milestone {
  phase: string;
  items: (ChecklistItem & { id: string; title: string })[];
}

function milestonesFromPayload(payload: unknown): Milestone[] {
  const p = payload as { milestones?: Milestone[] } | undefined;
  if (p?.milestones) return p.milestones;
  return [];
}

/** F-UI-1: 30-day timeline + optimistic checklist tick with rollback. */
export function Timeline() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["roadmap"],
    queryFn: api.getRoadmap,
  });
  const [failedId, setFailedId] = useState<string | null>(null);

  const milestones = useMemo(
    () => milestonesFromPayload(data?.json_payload),
    [data],
  );
  const allItems = useMemo(() => milestones.flatMap((m) => m.items), [milestones]);
  const progress = progressOf(allItems);

  const tick = useMutation({
    mutationFn: ({ id, completed }: { id: string; completed: boolean }) =>
      api.tickChecklist(id, completed),
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["roadmap"] });
      const prev = qc.getQueryData<Awaited<ReturnType<typeof api.getRoadmap>>>([
        "roadmap",
      ]);
      // Optimistic update: flip completed_at in cached roadmap
      qc.setQueryData(["roadmap"], (old: typeof prev) => {
        if (!old?.json_payload) return old;
        const payload = old.json_payload as { milestones: Milestone[] };
        return {
          ...old,
          json_payload: {
            ...payload,
            milestones: payload.milestones.map((m) => ({
              ...m,
              items: m.items.map((it) =>
                it.id === vars.id
                  ? {
                      ...it,
                      completed_at: vars.completed
                        ? new Date().toISOString()
                        : null,
                    }
                  : it,
              ),
            })),
          },
        };
      });
      return { prev };
    },
    onError: (_e, vars, ctx) => {
      // Rollback on 4xx/5xx + surface error
      if (ctx?.prev) qc.setQueryData(["roadmap"], ctx.prev);
      setFailedId(vars.id);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["roadmap"] }),
  });

  if (isLoading) return <div className="card" aria-busy="true">Loading roadmap…</div>;
  if (isError || !data)
    return (
      <div className="card" role="alert">
        Couldn&apos;t load your roadmap.{" "}
        <button className="btn-ghost ml-2" onClick={() => qc.invalidateQueries({ queryKey: ["roadmap"] })}>
          Retry
        </button>
      </div>
    );

  return (
    <section aria-label="30-day timeline" className="card">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Your first 30 days</h2>
        <span aria-label={`${progress}% complete`} className="text-sm text-slate-300">
          {progress}% complete
        </span>
      </div>
      <div
        className="mt-2 h-2 overflow-hidden rounded-full border border-white/10 bg-black/40"
        role="progressbar"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full shadow-glow-cyan" style={{ width: `${progress}%`, backgroundImage: "linear-gradient(90deg,#6366f1,#22d3ee)" }} />
      </div>

      {milestones.map((m) => (
        <div key={m.phase} className="mt-4">
          <h3 className="text-sm font-semibold uppercase tracking-widest text-indigo-200/80">
            {m.phase}
          </h3>
          <ul className="mt-1 divide-y divide-white/5">
            {m.items.map((item) => {
              const done = !!item.completed_at;
              return (
                <li key={item.id} className="flex items-center gap-3 py-2">
                  <input
                    type="checkbox"
                    checked={done}
                    disabled={tick.isPending}
                    aria-label={item.title}
                    onChange={(e) =>
                      tick.mutate({ id: item.id, completed: e.target.checked })
                    }
                    className="input-check"
                  />
                  <span className={done ? "text-slate-500 line-through" : "text-slate-100"}>
                    {item.title}
                  </span>
                  {item.mandatory ? (
                    <span className="badge border-amber-300/30 bg-amber-400/10 text-amber-200">mandatory</span>
                  ) : (
                    <span className="badge border-white/10 bg-white/[0.06] text-slate-300">optional</span>
                  )}
                  {failedId === item.id && (
                    <span role="alert" className="text-xs text-red-300">
                      Update failed — reverted. Retry.
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </section>
  );
}
