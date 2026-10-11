"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { PLAN_SECTIONS, lineDiff, sectionPayload, type PlanSection } from "@/lib/utils";

/**
 * F-UI-5: HITL editor — sectioned plan + citations, inline edit,
 * diff view, Approve & Execute confirm modal.
 */
export function PlanEditor({ caseId }: { caseId: string }) {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["plan", caseId],
    queryFn: () => api.getPlan(caseId),
  });
  const draft = useAppStore((s) => s.editorDraft);
  const setDraft = useAppStore((s) => s.setEditorDraft);
  const [editing, setEditing] = useState<PlanSection | null>(null);
  const [showDiff, setShowDiff] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const payload = useMemo(
    () => (data?.json_payload ?? {}) as Record<string, unknown>,
    [data],
  );

  useEffect(() => {
    if (data?.json_payload && !draft) {
      setDraft(structuredClone(data.json_payload) as Record<string, unknown>);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const save = useMutation({
    mutationFn: () => api.updatePlan(caseId, draft ?? payload),
    onSuccess: (plan) => {
      setNotice(`Saved as version ${plan.version}.`);
      qc.invalidateQueries({ queryKey: ["plan", caseId] });
    },
    onError: (e) => setNotice(e instanceof Error ? e.message : "Save failed"),
  });

  const approve = useMutation({
    mutationFn: (decision: "approve" | "reject") =>
      api.decideApproval(data?.id ?? "", { decision, comment }),
    onSuccess: (a) => {
      setConfirmOpen(false);
      setNotice(`Decision recorded: ${a.decision} (enqueues execute on approve).`);
      qc.invalidateQueries({ queryKey: ["cases"] });
    },
    onError: (e) => setNotice(e instanceof Error ? e.message : "Approval failed"),
  });

  if (isLoading) return <div className="card" aria-busy="true">Loading plan…</div>;
  if (isError || !data)
    return <div className="card" role="alert">Plan failed to load.</div>;

  const working = (draft ?? payload) as Record<string, unknown>;

  function updateSection(section: PlanSection, text: string) {
    try {
      const parsed: unknown = JSON.parse(text);
      if ("plan" in working && typeof working.plan === "object") {
        setDraft({ ...working, plan: { ...(working.plan as object), [section]: parsed } });
      } else {
        setDraft({ ...working, [section]: parsed });
      }
    } catch {
      // store raw text under a _raw key so nothing is lost; server validates
      setDraft({ ...working, [section]: text });
    }
  }

  return (
    <section aria-label="HITL plan editor" className="card">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">
          Plan review <span className="text-sm font-normal text-slate-400">v{data.version}</span>
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showDiff}
            onChange={(e) => setShowDiff(e.target.checked)}
          />
          Show diff
        </label>
      </div>
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}

      <div className="mt-3 space-y-4">
        {PLAN_SECTIONS.map((section) => {
          const original = JSON.stringify(sectionPayload(payload, section) ?? "(empty)", null, 2);
          const current = JSON.stringify(sectionPayload(working, section) ?? "(empty)", null, 2);
          const changed = original !== current;
          return (
            <details key={section} open className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
              <summary className="cursor-pointer font-medium text-slate-100">
                {section.replace(/_/g, " ")}
                {changed && <span className="badge ml-2 border-amber-300/30 bg-amber-400/10 text-amber-200">edited</span>}
              </summary>
              {editing === section ? (
                <div className="mt-2">
                  <label htmlFor={`edit-${section}`} className="sr-only">
                    Edit {section}
                  </label>
                  <textarea
                    id={`edit-${section}`}
                    className="input font-mono"
                    rows={8}
                    defaultValue={current}
                    onBlur={(e) => {
                      updateSection(section, e.target.value);
                      setEditing(null);
                    }}
                  />
                  <p className="faint mt-1 text-xs">JSON preferred; blur to apply.</p>
                </div>
              ) : (
                <div className="mt-2">
                  <pre className="pre-glass">{current}</pre>
                  <button className="btn-ghost mt-2 text-xs" onClick={() => setEditing(section)}>
                    Edit section
                  </button>
                </div>
              )}
              {showDiff && changed && (
                <div className="console mt-2" aria-label={`Diff for ${section}`}>
                  {lineDiff(original, current).map((d, i) => (
                    <div
                      key={i}
                      className={
                        d.type === "add"
                          ? "diff-add"
                          : d.type === "del"
                            ? "diff-del"
                            : "diff-ctx"
                      }
                    >
                      {d.type === "add" ? "+ " : d.type === "del" ? "− " : "  "}
                      {d.text}
                    </div>
                  ))}
                </div>
              )}
            </details>
          );
        })}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <button className="btn-ghost" onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save new version"}
        </button>
        <button className="btn-primary" onClick={() => setConfirmOpen(true)}>
          Approve &amp; Execute
        </button>
      </div>

      {confirmOpen && (
        <div role="dialog" aria-modal="true" aria-label="Confirm approval" className="fixed inset-0 z-40 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
          <div className="card w-full max-w-md shadow-glow motion-safe:animate-rise">
            <h3 className="text-lg font-semibold">Approve &amp; Execute?</h3>
            <p className="muted mt-1 text-sm">
              This enqueues deterministic execution (emails, invites, tickets). This cannot be undone
              from here — use Halt in Execution view to stop a runaway.
            </p>
            <label htmlFor="approve-comment" className="mt-3 block text-sm font-medium">
              Comment (optional)
            </label>
            <input
              id="approve-comment"
              className="input mt-1"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Looks good — ship it"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button className="btn-ghost" onClick={() => setConfirmOpen(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                disabled={approve.isPending}
                onClick={() => approve.mutate("approve")}
              >
                {approve.isPending ? "Approving…" : "Confirm approve"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
