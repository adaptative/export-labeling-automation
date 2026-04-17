/**
 * Prompt-eval API client (INT-013 · Sprint-16).
 *
 * Wraps ``/api/v1/evals`` — baseline eval results per agent plus a
 * ``Run All`` trigger that the UI can poll for batch progress.
 */
import { apiGet, apiPost } from './authInterceptor';

export type EvalStatus = 'pass' | 'fail' | 'warn' | 'running';

export interface EvalMetrics {
  precision: number;
  recall: number;
  f1_score: number;
  accuracy: number;
  cost_delta: number; // % change vs previous eval
  sample_size: number;
}

export interface ConfusionMatrix {
  true_positive: number;
  false_positive: number;
  true_negative: number;
  false_negative: number;
}

export interface EvalResult {
  id: string;
  agent_id: string;
  agent_name: string;
  batch_id?: string | null;
  eval_date: number; // unix seconds
  status: EvalStatus;
  metrics: EvalMetrics;
  confusion?: ConfusionMatrix | null;
  notes?: string | null;
}

export interface EvalListResponse {
  evals: EvalResult[];
  total: number;
}

export interface RunAllResponse {
  eval_batch_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  started_at: number;
}

export interface RunAllStatus {
  eval_batch_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  total: number;
  completed: number;
  failed: number;
  started_at: number;
  finished_at: number | null;
  results: EvalResult[];
}

export function listEvals(agentId?: string, limit = 100): Promise<EvalListResponse> {
  const q = new URLSearchParams();
  if (agentId) q.set('agent_id', agentId);
  if (limit) q.set('limit', String(limit));
  const qs = q.toString();
  return apiGet<EvalListResponse>(`/evals${qs ? `?${qs}` : ''}`);
}

export function getEval(evalId: string): Promise<EvalResult> {
  return apiGet<EvalResult>(`/evals/${encodeURIComponent(evalId)}`);
}

export function runAllEvals(): Promise<RunAllResponse> {
  return apiPost<RunAllResponse>('/evals/run-all');
}

export function getRunAllStatus(batchId: string): Promise<RunAllStatus> {
  return apiGet<RunAllStatus>(`/evals/run-all/${encodeURIComponent(batchId)}`);
}
