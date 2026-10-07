import type { ChecklistItem } from "./api.types";

export interface MilestoneItem extends ChecklistItem {
  id: string;
  title: string;
}

export function progressOf(items: { completed_at?: string | null }[]): number {
  if (items.length === 0) return 0;
  const done = items.filter((i) => !!i.completed_at).length;
  return Math.round((done / items.length) * 100);
}

/** Minimal line diff for HITL plan editor (added/removed lines). */
export function lineDiff(
  before: string,
  after: string,
): { type: "same" | "add" | "del"; text: string }[] {
  const a = before.split("\n");
  const b = new Set(after.split("\n"));
  const out: { type: "same" | "add" | "del"; text: string }[] = [];
  for (const line of a) {
    out.push({ type: b.has(line) ? "same" : "del", text: line });
  }
  const aSet = new Set(a);
  for (const line of after.split("\n")) {
    if (!aSet.has(line)) out.push({ type: "add", text: line });
  }
  return out;
}

/** Sections of a plan payload for the HITL editor. */
export const PLAN_SECTIONS = [
  "schedule",
  "welcome_email",
  "notion_spec",
  "invites",
  "tickets",
] as const;

export type PlanSection = (typeof PLAN_SECTIONS)[number];

export function sectionPayload(
  payload: Record<string, unknown> | undefined,
  section: PlanSection,
): unknown {
  if (!payload) return undefined;
  // Support both flat {schedule: ...} and nested {plan: {schedule: ...}} shapes
  if (section in payload) return payload[section];
  const nested = payload["plan"] as Record<string, unknown> | undefined;
  if (nested && section in nested) return nested[section];
  return undefined;
}
