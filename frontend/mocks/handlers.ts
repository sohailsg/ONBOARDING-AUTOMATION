import plan from "../../tests/fixtures/sample_plan.json";
import chat from "../../tests/fixtures/chat_sample.json";
import traces from "../../tests/fixtures/trace_events.json";
import { http, HttpResponse } from "msw";

const CASE = {
  id: "22222222-2222-4222-8222-222222222222",
  employee_id: "11111111-1111-4111-8111-111111111111",
  status: "awaiting_hr_approval",
  current_plan_version: 1,
  idempotency_key: "emp-0001_2026-11-01",
};

/** MSW handlers mirror backend/openapi.yaml shapes — regenerated, not hand-shaped. */
export const handlers = [
  http.get("*/api/v1/cases", ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get("status");
    const items = status && status !== CASE.status ? [] : [CASE];
    return HttpResponse.json({ items });
  }),
  http.get("*/api/v1/cases/:id/plan", () =>
    HttpResponse.json({ id: plan.plan_id, case_id: plan.case_id, version: 1, json_payload: plan, created_by: "agent" }),
  ),
  http.put("*/api/v1/cases/:id/plan", async ({ request }) => {
    const body = (await request.json()) as { json_payload: unknown };
    return HttpResponse.json({ id: "new-plan-id", version: 2, json_payload: body.json_payload, created_by: "hr_user" });
  }),
  http.post("*/api/v1/approvals/:id", async ({ request }) => {
    const body = (await request.json()) as { decision: string };
    return HttpResponse.json({ id: "approval-1", decision: body.decision, decided_at: new Date().toISOString() });
  }),
  http.get("*/api/v1/me/roadmap", () =>
    HttpResponse.json({ id: plan.plan_id, version: 1, json_payload: plan, created_by: "agent" }),
  ),
  http.patch("*/api/v1/me/checklist/:id", ({ params }) =>
    HttpResponse.json({ id: params.id, title: "demo", completed_at: new Date().toISOString() }),
  ),
  http.post("*/api/v1/chat", () => HttpResponse.json(chat)),
  http.get("*/api/v1/cases/:id/stream", () =>
    HttpResponse.json(traces),
  ),
  http.post("*/api/v1/auth/dev-login", async ({ request }) => {
    const body = (await request.json()) as { role?: string };
    const role = body.role === "hr_admin" ? "hr_admin" : "employee";
    const sub = role === "hr_admin" ? "hr-1" : CASE.employee_id;
    return HttpResponse.json({ token: `dev:${role}:${sub}`, role, sub });
  }),
];
