// GENERATED from control/*.py — do not edit; run tools/gen_ts_contracts.py

export interface Actor {
  type: string;
  id: string;
}

export interface TraceContext {
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
}

export interface RedactionInfo {
  level: string;
  has_secret: boolean;
  redacted_fields: string[];
}

export interface RuntimeEvent {
  event_type: string;
  session_id: string;
  actor: Actor;
  trace: TraceContext;
  redaction: RedactionInfo;
  event_id: string;
  created_at: string;
  schema_version: number;
  seq: number;
  round_no: number | null;
  workflow_id: string | null;
  task_id: string | null;
  source: string;
  payload: Record<string, unknown>;
  ui_payload: Record<string, unknown> | null;
}

export interface IssuedBy {
  type: string;
  user_id: string | null;
  agent_id: string | null;
}

export interface RuntimeCommand {
  command_type: string;
  session_id: string;
  issued_by: IssuedBy;
  idempotency_key: string;
  payload: Record<string, unknown>;
  command_id: string;
  created_at: string;
  schema_version: number;
}

export interface CommandAck {
  command_id: string;
  status: string;
  seq: number | null;
  rejection_reason: string | null;
  created_at: string;
}

export interface RuntimeCheckpoint {
  checkpoint_type: string;
  session_id: string;
  risk_level: string;
  status: string;
  payload: Record<string, unknown>;
  checkpoint_id: string;
  created_at: string;
  resolved_at: string | null;
}

export interface Permission {
  allowed_tools: string[];
  can_write_artifacts: boolean;
  can_call_other_agents: boolean;
  can_execute_shell: boolean;
  can_modify_workflow: boolean;
  can_modify_permissions: boolean;
  effective_from: string;
}

export interface AgentView {
  agent_id: string;
  role: string;
  status: string;
  round_no: number;
  allowed_tools: string[];
  last_output_summary: string;
  context_packet: Record<string, unknown>;
  permission: Record<string, unknown> | null;
}

export interface TaskLoopSnapshot {
  session_id: string;
  status: string;
  round_no: number;
  orchestrator: Record<string, string>;
  agents: AgentView[];
  pending_agent_calls: Record<string, unknown>[];
  tool_calls: Record<string, unknown>[];
  checkpoints: Record<string, unknown>[];
  acceptance_status: Record<string, unknown>[];
  last_updated_at: string;
}
