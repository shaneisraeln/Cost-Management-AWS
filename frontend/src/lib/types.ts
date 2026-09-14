// Types mirroring the backend Pydantic schemas.

export type ConnectionStatus =
  | "PENDING"
  | "CONNECTED"
  | "DEGRADED"
  | "ERROR";

export type ConnectionAuthMode = "LOCAL_PROFILE" | "ASSUME_ROLE";

export interface ConnectionSetupInfo {
  assume_role_available: boolean;
  app_principal_arn: string | null;
  external_id: string;
  region: string;
  read_policy: Record<string, unknown>;
  trust_policy: Record<string, unknown> | null;
  prerequisite_note: string | null;
}

export interface AwsConnection {
  id: string;
  account_id: string | null;
  auth_mode: ConnectionAuthMode;
  profile_name: string | null;
  role_arn: string | null;
  external_id: string | null;
  region: string;
  status: ConnectionStatus;
  read_only: boolean;
  permission_status: Record<string, boolean>;
  last_cost_sync: string | null;
  last_resource_sync: string | null;
  last_event_sync: string | null;
  last_metrics_sync: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface PermissionStatus {
  capability: string;
  label: string;
  available: boolean;
  detail: string | null;
}

export interface ValidationResult {
  account_id: string | null;
  status: ConnectionStatus;
  permissions: PermissionStatus[];
  error_message: string | null;
}

// --- Cost types (mirror backend schemas/cost.py) ---

export interface CostSummary {
  period_start: string;
  period_end: string;
  total: string; // Decimal serialized as string
  currency: string;
  record_count: number;
}

export interface DailyCostPoint {
  date: string;
  amount: string;
}

export interface ServiceBreakdownItem {
  service: string;
  amount: string;
}

export interface CostBreakdown {
  period_start: string;
  period_end: string;
  currency: string;
  by_service: ServiceBreakdownItem[];
}

export interface CostSyncResult {
  account_id: string | null;
  period_start: string;
  period_end: string;
  lines_fetched: number;
  records_upserted: number;
  total: string;
  currency: string;
}

// --- Resource types (mirror backend schemas/resource.py) ---

export interface Resource {
  id: string;
  account_id: string | null;
  provider: string;
  provider_resource_id: string;
  arn: string | null;
  service: string;
  resource_type: string;
  region: string | null;
  state: string | null;
  provider_created_at: string | null;
  tags: Record<string, string>;
  resource_metadata: Record<string, unknown>;
  owner_id: string | null;
  project_id: string | null;
  environment: string | null;
  attribution_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResourceSyncResult {
  account_id: string | null;
  discovered: number;
  upserted: number;
  by_service: Record<string, number>;
}

// --- Attribution / reconciliation types ---

export type AttributionStatus =
  | "ATTRIBUTED"
  | "SHARED"
  | "UNKNOWN"
  | "DISPUTED";

export interface EvidenceItem {
  type: string;
  weight: number;
  detail: string;
}

export interface Attribution {
  id: string;
  resource_id: string;
  owner_label: string | null;
  project_id: string | null;
  environment: string | null;
  status: AttributionStatus;
  confidence: number;
  source: string | null;
  evidence: EvidenceItem[];
  is_manual: boolean;
  valid_from: string | null;
  created_at: string;
}

export interface Reconciliation {
  total: string;
  attributed: string;
  shared: string;
  unknown: string;
  currency: string;
  coverage: number;
  reconciles: boolean;
}

export interface OwnerSummary {
  owners: { owner_label: string; resource_count: number }[];
  unknown_count: number;
  shared_count: number;
}

// --- Investigation types ---

export type ChangeClassification =
  | "GROWTH"
  | "ENGINEERING_CHANGE"
  | "WASTE"
  | "SUSPICIOUS"
  | "UNKNOWN";

export interface CostChange {
  id: string;
  period_date: string;
  service: string | null;
  baseline_cost: string;
  observed_cost: string;
  absolute_change: string;
  percentage_change: number | null;
  classification: ChangeClassification;
  confidence: number;
  evidence: Array<Record<string, unknown>>;
  created_at: string;
}

export interface Anomaly {
  id: string;
  service: string | null;
  detected_for: string;
  severity: "LOW" | "MEDIUM" | "HIGH";
  baseline: string;
  observed: string;
  difference: string;
  algorithm: string;
  confidence: number;
  status: string;
  evidence: Array<Record<string, unknown>>;
  created_at: string;
}

export interface TimelineItem {
  kind: "event" | "anomaly" | "cost_change";
  timestamp: string | null;
  title: string;
  detail: Record<string, unknown>;
}

export interface Explanation {
  text: string;
  generated_by: "ai" | "template";
}

export interface DetectionResult {
  anomalies_created: number;
  cost_changes_created: number;
  services_analyzed: number;
}

// --- GitHub / cost estimate types ---

export interface GithubRepository {
  id: string;
  full_name: string;
  project_id: string | null;
  environment: string | null;
  created_at: string;
}

export interface EstimateLineItem {
  address: string;
  iac_type: string;
  service: string;
  action: string;
  baseline_monthly: string;
  proposed_monthly: string;
  delta_monthly: string;
  estimated: boolean;
  detail: string;
}

export interface CostEstimate {
  id: string;
  repository_id: string | null;
  pr_number: number | null;
  base_commit: string | null;
  head_commit: string | null;
  account_id: string | null;
  project_id: string | null;
  environment: string | null;
  deployed_at: string | null;
  baseline_monthly: string;
  proposed_monthly: string;
  estimated_monthly_delta: string;
  currency: string;
  line_items: EstimateLineItem[];
  unsupported: string[];
  iac_format: string;
  pricing_source: string | null;
  status: string;
  created_at: string;
}

export type VarianceVerdict =
  | "HIGHER"
  | "LOWER"
  | "CLOSE"
  | "INSUFFICIENT_DATA";

export interface ServiceObservation {
  service: string;
  observed_window: string;
  observed_monthly: string;
}

export interface Variance {
  estimate_id: string;
  predicted_monthly: string;
  actual_monthly: string;
  absolute_variance: string;
  percentage_variance: number | null;
  verdict: VarianceVerdict;
  actual_days_observed: number;
  possible_reasons: string[];
  is_causal_claim: boolean;
  window_start: string;
  window_end: string;
  account_scoped: boolean;
  service_breakdown: ServiceObservation[];
  note: string;
}

// --- Cost Guardrail types ---

export type GuardrailStatus = "PASS" | "WARNING" | "REVIEW_REQUIRED";

export interface CostDriver {
  address: string;
  detail: string;
  delta_monthly: string;
}

export interface Guardrail {
  estimate_id: string;
  status: GuardrailStatus;
  monthly_delta: string;
  currency: string;
  baseline_monthly: string;
  proposed_monthly: string;
  warning_threshold: string;
  review_threshold: string;
  threshold: string | null;
  message: string;
  is_savings: boolean;
  estimate_complete: boolean;
  incomplete_note: string | null;
  unsupported: string[];
  pricing_source: string | null;
  cost_drivers: CostDriver[];
  evaluated_at: string;
  is_estimate: boolean;
}

// --- Remediation types ---

export interface PolicyCheck {
  check: string;
  passed: boolean;
  detail: string;
}

export interface RemediationPreview {
  resource_id: string;
  provider_resource_id: string | null;
  service: string | null;
  current_state: string | null;
  proposed_action: string;
  allowed: boolean;
  reasons: string[];
  checks: PolicyCheck[];
}

export type ActionStatus = "PENDING" | "BLOCKED" | "FAILED" | "EXECUTED";

export interface ActionRequest {
  id: string;
  action_type: string;
  resource_id: string | null;
  provider_resource_id: string | null;
  region: string | null;
  requested_by: string;
  status: ActionStatus;
  policy_result: Record<string, unknown>;
  result: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  action: string;
  resource_id: string | null;
  aws_api: string | null;
  request_summary: string | null;
  result: string;
  detail: Record<string, unknown>;
  created_at: string;
}

// --- Bedrock intelligence types ---

export interface BedrockCostFacts {
  available: boolean;
  total_cost: string;
  currency: string;
  source: string;
  reason: string | null;
}

export interface BedrockUsageFacts {
  available: boolean;
  source: string;
  invocations: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  metrics_present: string[];
  reason: string | null;
}

export interface BedrockModelUsage {
  model_id: string;
  invocations: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface BedrockEfficiency {
  is_calculated: boolean;
  cost_per_invocation: string | null;
  tokens_per_invocation: string | null;
  note: string;
}

export interface BedrockSpike {
  detected: boolean;
  metric: string | null;
  day: string | null;
  baseline: string | null;
  observed: string | null;
  difference: string | null;
  associated_cost_change: string | null;
  message: string | null;
  reason: string | null;
}

export interface BedrockIntelligence {
  period_start: string;
  period_end: string;
  cost: BedrockCostFacts;
  usage: BedrockUsageFacts;
  by_model: BedrockModelUsage[];
  efficiency: BedrockEfficiency;
  spike: BedrockSpike;
  has_any_data: boolean;
  notes: string[];
}
