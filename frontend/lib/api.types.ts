// AUTO-GENERATED from backend/openapi.yaml — do not edit. Regenerate: make gen-api
export type ActionPayload = {
  idempotency_key?: string;
  payload?: Record<string, unknown>;
  type: string;
};
export type Approval = {
  approver_id: string;
  decided_at: string;
  decision: string;
  id: string;
  plan_id: string;
};
export type ApprovalDecision = {
  comment?: string;
  decision: 'approve' | 'reject';
};
export type Case = {
  current_plan_version: number;
  employee_id: string;
  id: string;
  idempotency_key: string;
  session_id?: string;
  status: CaseStatus;
};
export type CasePage = {
  items: Case[];
  page: number;
  page_size: number;
  total: number;
};
export type CaseStatus = 'pending_ingestion' | 'agent_processing' | 'awaiting_hr_approval' | 'executing' | 'needs_attention' | 'active';
export type ChatRequest = {
  question: string;
};
export type ChatResponse = {
  answer: string;
  citations: Citation[];
  confidence: number;
};
export type ChecklistItem = {
  completed_at: string;
  due_day: number;
  id: string;
  mandatory: boolean;
  title: string;
};
export type ChecklistPatch = {
  completed: boolean;
};
export type Citation = {
  doc: string;
  effective_date?: string;
  page?: number;
};
export type DevLoginIn = {
  employee_id?: string;
  role: 'employee' | 'hr_admin';
};
export type DevLoginOut = {
  role: string;
  sub: string;
  token: string;
};
export type HTTPValidationError = {
  detail?: ValidationError[];
};
export type HireRecord = {
  buddy_id?: string;
  dept?: string;
  manager_id?: string;
  name: string;
  region?: string;
  role?: string;
  start_date: string;
  timezone?: string;
};
export type Plan = {
  actions?: Record<string, unknown>[];
  case_id: string;
  created_by: string;
  id: string;
  json_payload: Record<string, unknown>;
  version: number;
};
export type PlanIn = {
  actions?: ActionPayload[];
  json_payload?: Record<string, unknown>;
};
export type TraceEvent = {
  case_id: string;
  id?: number;
  message: string;
  session_id: string;
  step: string;
  ts: string;
};
export type ValidationError = {
  ctx?: Record<string, unknown>;
  input?: Record<string, unknown>;
  loc: string | number[];
  msg: string;
  type: string;
};

export const ApiRoutes = {
  audit_completeness_api_v1_admin_audit_completeness__case_id__get: '/api/v1/admin/audit/completeness/{case_id}',
  audit_export_api_v1_admin_audit_export_get: '/api/v1/admin/audit/export',
  dlq_list_api_v1_admin_dlq_get: '/api/v1/admin/dlq',
  dlq_drain_api_v1_admin_dlq_drain_post: '/api/v1/admin/dlq/drain',
  kill_switch_clear_api_v1_admin_kill_switch__case_id__delete: '/api/v1/admin/kill-switch/{case_id}',
  kill_switch_halt_api_v1_admin_kill_switch__case_id__post: '/api/v1/admin/kill-switch/{case_id}',
  readiness_api_v1_admin_readiness_get: '/api/v1/admin/readiness',
  reindex_api_v1_admin_reindex_post: '/api/v1/admin/reindex',
  retention_dry_run_api_v1_admin_retention_dry_run_get: '/api/v1/admin/retention/dry-run',
  decide_approval_api_v1_approvals__plan_id__post: '/api/v1/approvals/{plan_id}',
  dev_login_api_v1_auth_dev_login_post: '/api/v1/auth/dev-login',
  whoami_api_v1_auth_whoami_get: '/api/v1/auth/whoami',
  list_cases_api_v1_cases_get: '/api/v1/cases',
  get_plan_api_v1_cases__case_id__plan_get: '/api/v1/cases/{case_id}/plan',
  update_plan_api_v1_cases__case_id__plan_put: '/api/v1/cases/{case_id}/plan',
  stream_trace_api_v1_cases__case_id__stream_get: '/api/v1/cases/{case_id}/stream',
  policy_chat_api_v1_chat_post: '/api/v1/chat',
  halt_execution_api_v1_execute__case_id__halt_post: '/api/v1/execute/{case_id}/halt',
  tick_checklist_api_v1_me_checklist__item_id__patch: '/api/v1/me/checklist/{item_id}',
  get_roadmap_api_v1_me_roadmap_get: '/api/v1/me/roadmap',
  trigger_onboarding_api_v1_onboarding_trigger_post: '/api/v1/onboarding/trigger',
  health_health_get: '/health',
  metrics_metrics_get: '/metrics',
};
