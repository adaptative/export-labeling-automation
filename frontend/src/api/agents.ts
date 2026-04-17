/**
 * Agent inspector API client (INT-013 · Sprint-16).
 *
 * Wraps ``/api/v1/agents`` — the live catalogue of 14 Labelforge agents
 * and their per-process telemetry (calls, success rate, p95 latency,
 * cumulative cost).
 */
import { apiGet } from './authInterceptor';

export type AgentStatus = 'healthy' | 'degraded' | 'idle';

export type AgentKind =
  | 'intake'
  | 'orchestration'
  | 'fusion'
  | 'compliance'
  | 'composition'
  | 'hitl'
  | 'guardrail'
  | 'output'
  | 'notification';

export interface AgentCard {
  agent_id: string;
  name: string;
  kind: AgentKind;
  status: AgentStatus;
  calls: number;
  successes: number;
  failures: number;
  success_rate: number; // 0..1
  avg_latency_ms: number;
  total_cost_usd: number;
  last_call_at: number | null; // unix seconds
}

export interface AgentListResponse {
  agents: AgentCard[];
  total: number;
}

export function listAgents(): Promise<AgentListResponse> {
  return apiGet<AgentListResponse>('/agents');
}

export function getAgent(agentId: string): Promise<AgentCard> {
  return apiGet<AgentCard>(`/agents/${encodeURIComponent(agentId)}`);
}
