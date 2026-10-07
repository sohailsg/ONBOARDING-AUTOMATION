import type {
  Approval,
  ApprovalDecision,
  Case,
  CaseStatus,
  ChatRequest,
  ChatResponse,
  ChecklistItem,
  Plan,
} from "./api.types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const OPENAPI_HASH = "0.0.0-w0-stub"; // bumped by `npm run gen-api`; client shows drift banner on mismatch

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include", // httpOnly JWT cookie; never touch localStorage
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
    ...init,
  });
  if (res.status === 403) throw new Error("Forbidden — contact HR.");
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body || res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listCases: (status?: CaseStatus) =>
    request<{ items: Case[] }>(
      `/api/v1/cases${status ? `?status=${encodeURIComponent(status)}` : ""}`,
    ),
  getPlan: (caseId: string) =>
    request<Plan>(`/api/v1/cases/${caseId}/plan`),
  updatePlan: (caseId: string, json_payload: Record<string, unknown>) =>
    request<Plan>(`/api/v1/cases/${caseId}/plan`, {
      method: "PUT",
      body: JSON.stringify({ json_payload }),
    }),
  decideApproval: (planId: string, decision: ApprovalDecision) =>
    request<Approval>(`/api/v1/approvals/${planId}`, {
      method: "POST",
      body: JSON.stringify(decision),
    }),
  getRoadmap: () => request<Plan>(`/api/v1/me/roadmap`),
  tickChecklist: (id: string, completed: boolean) =>
    request<ChecklistItem>(`/api/v1/me/checklist/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ completed }),
    }),
  policyChat: (body: ChatRequest) =>
    request<ChatResponse>(`/api/v1/chat`, {
      method: "POST",
      body: JSON.stringify(body),
      // NOTE: region/dept are resolved server-side from the profile.
      // Never send them from the client (spec 06 §2 constraint).
    }),
  reindex: () =>
    request<void>(`/api/v1/admin/reindex`, { method: "POST" }),
};

export function streamUrl(caseId: string): string {
  // EventSource cannot set Authorization headers → cookie auth (or
  // signed-URL fallback per 02 T-3). Query param added only when the
  // backend issues a short-lived stream token.
  return `${API_BASE}/api/v1/cases/${caseId}/stream`;
}
