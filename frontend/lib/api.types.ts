// AUTO-GENERATED from backend/openapi.yaml — do not edit. Regenerate: make gen-api
export type CaseStatus = 'pending_ingestion' | 'agent_processing' | 'awaiting_hr_approval' | 'executing' | 'needs_attention' | 'active';
export type HireRecord = {
  name: string;
  role: string;
  dept: string;
  region: string;
  timezone?: string;
  manager_id?: string;
  buddy_id?: string;
  start_date: string;
};
export type Case = {
  id?: string;
  employee_id?: string;
  status?: CaseStatus;
  current_plan_version?: number;
  idempotency_key?: string;
};
export type Plan = {
  id?: string;
  case_id?: string;
  version?: number;
  json_payload?: Record<string, unknown>;
  created_by?: 'agent' | 'hr_user';
};
export type ApprovalDecision = {
  decision: 'approve' | 'reject';
  comment?: string;
};
export type Approval = {
  id?: string;
  plan_id?: string;
  approver_id?: string;
  decision?: string;
  decided_at?: string;
};
export type ChecklistItem = {
  id?: string;
  title?: string;
  due_day?: number;
  mandatory?: boolean;
  completed_at?: string;
};
export type ChatRequest = {
  question: string;
};
export type ChatResponse = {
  answer?: string;
  citations?: {
  doc?: string;
  page?: number;
  effective_date?: string;
}[];
  confidence?: number;
};
export type TraceEvent = {
  ts?: string;
  step?: string;
  message?: string;
  case_id?: string;
  session_id?: string;
};

export const ApiRoutes = {
  triggerOnboarding: '/api/v1/onboarding/trigger',
  listCases: '/api/v1/cases',
  streamTrace: '/api/v1/cases/{id}/stream',
  getPlan: '/api/v1/cases/{id}/plan',
  updatePlan: '/api/v1/cases/{id}/plan',
  decideApproval: '/api/v1/approvals/{plan_id}',
  getRoadmap: '/api/v1/me/roadmap',
  tickChecklist: '/api/v1/me/checklist/{id}',
  policyChat: '/api/v1/chat',
  reindex: '/api/v1/admin/reindex',
};
