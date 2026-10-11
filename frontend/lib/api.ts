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
  process.env.NEXT_PUBLIC_API_URL ?? "";
// Empty base = same-origin: Next rewrites /api/* to the gateway server-side
// (required for public/tunnel links; the browser can't reach backend ports).

export const OPENAPI_HASH = "0.2.0-w2"; // bumped by `npm run gen-api`; client shows drift banner on mismatch

// Dev-credential holder. Prod uses an httpOnly JWT cookie (untouched here);
// the SSO stub has no cookie the API accepts, so the dev-login token lives
// in memory (+ sessionStorage so refresh keeps working). Never localStorage.
let apiToken = "";
if (typeof sessionStorage !== "undefined") {
  apiToken = sessionStorage.getItem("ob_api_token") ?? "";
}
export function setApiToken(token: string) {
  apiToken = token;
  try {
    if (token) sessionStorage.setItem("ob_api_token", token);
    else sessionStorage.removeItem("ob_api_token");
  } catch {
    /* private mode etc. — memory still works */
  }
}
export function getApiToken() {
  return apiToken;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: "include", // httpOnly JWT cookie; never touch localStorage
    headers: {
      "Content-Type": "application/json",
      ...(apiToken ? { Authorization: `Bearer ${apiToken}` } : {}),
      ...(init.headers ?? {}),
    },
    ...init,
  });
  if (res.status === 403) throw new Error("Forbidden — contact HR.");
  if (res.status === 401 && typeof window !== "undefined") {
    // Credential lost (new tab, HMR module reset, cleared storage) while the
    // role cookie survived: drop the dead token and bounce to sign-in rather
    // than surfacing raw 401s on every widget.
    if (!window.location.pathname.startsWith("/login")) {
      setApiToken("");
      window.location.href =
        `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
    throw new Error("Signed out — please sign in again.");
  }
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
  devLogin: (role: string) =>
    request<{ token: string; role: string; sub: string }>(
      `/api/v1/auth/dev-login`,
      { method: "POST", body: JSON.stringify({ role }) },
    ),
};

export function streamUrl(caseId: string): string {
  // EventSource cannot set Authorization headers → pass the dev token as
  // ?token= (backend 2b fallback, 02 T-3). Prod uses the httpOnly cookie.
  const token = getApiToken();
  const qs = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${API_BASE}/api/v1/cases/${caseId}/stream${qs}`;
}
