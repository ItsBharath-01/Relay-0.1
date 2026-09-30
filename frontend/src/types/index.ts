export type LanguageCode = "en" | "hi" | "kn" | "ta" | "te" | "ml" | "bn";

export interface UserPreference {
  language: LanguageCode;
  auto_recover: boolean;
  ask_external_messages: boolean;
  ask_payments: boolean;
  ask_purchases: boolean;
  ask_deleting: boolean;
  ask_sensitive_info: boolean;
  threshold_people: number;
  threshold_amount: number;
}

export interface User {
  id: string;
  email: string;
  name: string;
  is_active: boolean;
  created_at: string;
  preferences?: UserPreference;
}

export interface ClarificationOption {
  id: string;
  label: string;
}

export interface ClarificationQuestion {
  id: string;
  question: string;
  options: ClarificationOption[];
  allow_custom: boolean;
}

export interface GoalUnderstanding {
  objective: string;
  constraints: string[];
  participants: string[];
  deadline?: string | null;
  required_capabilities: string[];
  missing_information: string[];
  clarification_needed: boolean;
  clarification_questions: ClarificationQuestion[];
}

export interface Goal {
  id: string;
  text: string;
  language: string;
  attachments?: string[];
  links?: string[];
  deadline?: string | null;
  status: string;
  understanding?: GoalUnderstanding;
  clarifications?: Record<string, string>;
  created_at: string;
}

export interface ToolCheckResult {
  tool_id: string;
  tool_name: string;
  tool_type: string;
  is_connected: boolean;
  is_authorized: boolean;
  is_available: boolean;
  is_compatible: boolean;
  passed_all: boolean;
  ruled_out_reason?: string | null;
}

export interface SelectionDecisionRecord {
  task_id?: string | null;
  capability_id: string;
  candidate_checks: ToolCheckResult[];
  selected_tool_id?: string | null;
  selected_tool_name?: string | null;
  explanation: string;
}

export interface PlanTask {
  id: string;
  order: number;
  title: string;
  capability_id: string;
  candidate_tool_ids: string[];
  depends_on: string[];
  risk_level: "low" | "medium" | "high" | "critical";
  requires_approval: boolean;
  status: "pending" | "running" | "completed" | "failed" | "recovering" | "waiting_approval" | "rejected";
  has_connected_tool: boolean;
  selected_tool_id?: string | null;
  selected_tool_name?: string | null;
  action?: string;
  params?: Record<string, any>;
}

export interface Plan {
  id: string;
  goal_id: string;
  version: number;
  tasks: PlanTask[];
  all_tools_available: boolean;
  missing_capabilities: string[];
}

export interface ExecutionEvent {
  id: string;
  seq: number;
  type: string;
  timestamp: string;
  task_id?: string | null;
  tool_id?: string | null;
  message: string;
  params?: Record<string, any>;
  payload?: Record<string, any>;
}

export interface Approval {
  id: string;
  execution_id: string;
  task_id: string;
  action: string;
  target?: string | null;
  content: Record<string, any>;
  payload_hash: string;
  reason: string;
  risk: "low" | "medium" | "high" | "critical";
  consequences?: string | null;
  status: "pending" | "approved" | "rejected" | "expired";
  decided_by?: string | null;
  created_at: string;
}

export interface Recovery {
  id: string;
  task_id: string;
  original_tool_id: string;
  problem: string;
  alternative_tool_id?: string | null;
  reason: string;
  status: "pending" | "succeeded" | "failed";
  created_at: string;
}

export interface Verification {
  id: string;
  task_id: string;
  criterion: string;
  result: "passed" | "failed";
  evidence: Record<string, any>;
  created_at: string;
}

export interface ExecutionDetail {
  id: string;
  goal_id: string;
  goal_text: string;
  plan_id: string;
  status: "running" | "paused" | "waiting_approval" | "completed" | "failed" | "cancelled" | "stopped";
  progress: number;
  current_task_id?: string | null;
  current_action?: string | null;
  started_at: string;
  completed_at?: string | null;
  events: ExecutionEvent[];
  approvals: Approval[];
  recoveries: Recovery[];
  verifications: Verification[];
}

export interface Permission {
  id: string;
  key: string;
  label: string;
  is_granted: boolean;
  is_sensitive: boolean;
}

export interface Connection {
  id: string;
  app_id: string;
  name: string;
  status: "connected" | "not_connected" | "needs_reconnection" | "error" | "coming_soon";
  auth_type: string;
  has_credentials: boolean;
  permissions: Permission[];
}

export interface LLMHealth {
  provider: string;
  model: string;
  reachable: boolean;
  available: boolean;
  status: "ready" | "unavailable" | "model_missing" | "error" | "backend_unavailable";
  error?: string | null;
  details?: Record<string, any>;
}

export type VoiceState =
  | "idle"
  | "listening"
  | "transcribing"
  | "processing"
  | "confirmation_required"
  | "speaking"
  | "error";

export interface VoiceCommandResponse {
  transcript: string;
  intent: string;
  reply_text: string;
  action_taken?: string | null;
  execution_id?: string | null;
  confidence: number;
  clarification_needed: boolean;
  clarification_question?: string | null;
  llm_used: boolean;
}
