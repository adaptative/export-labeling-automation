/**
 * Compliance rule hooks (Sprint 11 / INT-010).
 *
 * Thin wrappers around `/api/v1/rules/*`. Each mutation invalidates the
 * relevant query keys so the page and detail panel stay in sync.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiGet, apiPost, apiPut } from '@/api/authInterceptor';

/* ── Types ─────────────────────────────────────────────────────────────── */

export interface ComplianceRule {
  id: string;
  code: string;
  version: number;
  title: string;
  description: string;
  region: string;
  placement: string;
  active: boolean;
  logic?: RuleLogic | null;
  updated_at: string;
}

export interface RuleListResponse {
  rules: ComplianceRule[];
  total: number;
}

/**
 * Shape of the `logic` column. The DSL matches the backend compiler
 * (labelforge/compliance/rule_engine.py).
 */
export interface RuleLogic {
  conditions?: RuleNode | null;
  requirements?: RuleNode | null;
  category?: string | null;
  [k: string]: unknown;
}

export interface RuleNode {
  op: string;
  field?: string;
  value?: unknown;
  values?: unknown[];
  child?: RuleNode;
  children?: RuleNode[];
}

export interface RuleFilters {
  region?: string;
  placement?: string;
  active?: boolean;
  code?: string;
  limit?: number;
  offset?: number;
}

export interface RuleCreatePayload {
  code: string;
  title: string;
  description?: string;
  region?: string;
  placement?: string;
  logic?: RuleLogic | null;
}

export interface RuleUpdatePayload {
  title?: string;
  description?: string;
  region?: string;
  placement?: string;
  logic?: RuleLogic | null;
}

export interface DryRunPayload {
  proposed: RuleCreatePayload;
  order_id?: string;
  item_ids?: string[];
  sample_contexts?: Array<Record<string, unknown>>;
}

export interface DryRunResponse {
  items_evaluated: number;
  newly_failing: string[];
  newly_passing: string[];
  unchanged: string[];
}

export interface RuleMutationResponse {
  rule_id: string;
  code: string;
  version: number;
  active: boolean;
  message: string;
}

export interface RuleAuditEntry {
  id: string;
  action: string;
  actor?: string | null;
  actor_type: string;
  rule_id?: string | null;
  detail?: string | null;
  created_at: string;
}

export interface RuleAuditLogResponse {
  entries: RuleAuditEntry[];
  total: number;
}

/* ── Queries ───────────────────────────────────────────────────────────── */

function buildQuery(filters?: RuleFilters): string {
  if (!filters) return '';
  const params = new URLSearchParams();
  if (filters.region) params.set('region', filters.region);
  if (filters.placement) params.set('placement', filters.placement);
  if (filters.active !== undefined) params.set('active', String(filters.active));
  if (filters.code) params.set('code', filters.code);
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

export function useRules(filters?: RuleFilters) {
  return useQuery({
    queryKey: ['rules', filters ?? {}],
    queryFn: () => apiGet<RuleListResponse>(`/rules${buildQuery(filters)}`),
  });
}

export function useRule(ruleId: string | null | undefined) {
  return useQuery({
    queryKey: ['rules', ruleId],
    enabled: !!ruleId,
    queryFn: () => apiGet<ComplianceRule>(`/rules/${ruleId}`),
  });
}

/**
 * Audit-log view for a single rule (pass `ruleId`) or the whole tenant
 * (leave undefined).
 */
export function useRuleAuditLog(ruleId?: string | null, opts?: { limit?: number; offset?: number }) {
  const params = new URLSearchParams();
  if (ruleId) params.set('rule_id', ruleId);
  if (opts?.limit !== undefined) params.set('limit', String(opts.limit));
  if (opts?.offset !== undefined) params.set('offset', String(opts.offset));
  const qs = params.toString();
  return useQuery({
    queryKey: ['rules', 'audit-log', ruleId ?? 'all', opts ?? {}],
    queryFn: () => apiGet<RuleAuditLogResponse>(`/rules/audit-log${qs ? `?${qs}` : ''}`),
  });
}

/* ── Mutations ─────────────────────────────────────────────────────────── */

export function useCreateRuleMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RuleCreatePayload) => apiPost<ComplianceRule>('/rules', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

export function useUpdateRuleMutation(ruleId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RuleUpdatePayload) => apiPut<ComplianceRule>(`/rules/${ruleId}`, body),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ['rules'] });
      if (updated?.id) {
        qc.setQueryData(['rules', updated.id], updated);
      }
    },
  });
}

export function useDryRunRuleMutation() {
  return useMutation({
    mutationFn: (body: DryRunPayload) => apiPost<DryRunResponse>('/rules/dry-run', body),
  });
}

export function usePromoteRuleMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) => apiPost<RuleMutationResponse>(`/rules/${ruleId}/promote`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

export function useRollbackRuleMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (ruleId: string) => apiPost<RuleMutationResponse>(`/rules/${ruleId}/rollback`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['rules'] });
    },
  });
}

/* ── DSL helpers ───────────────────────────────────────────────────────── */

/**
 * Render a `RuleNode` DSL AST back to the text form used in the editor.
 * Kept intentionally simple: good enough for staged rules round-tripping
 * through the form without mutation.
 */
export function dslToText(node: RuleNode | null | undefined): string {
  if (!node) return '';
  const op = node.op;
  if (op === 'true') return 'true';
  if (op === 'AND' || op === 'OR') {
    const parts = (node.children ?? []).map(dslToText).filter(Boolean);
    if (parts.length === 0) return '';
    return parts.map((p) => `(${p})`).join(` ${op} `);
  }
  if (op === 'NOT') {
    const inner = dslToText(node.child ?? null);
    return inner ? `NOT (${inner})` : '';
  }
  if (op === 'in' || op === 'not_in') {
    const vals = (node.values ?? []).map(formatLiteral).join(', ');
    return `${node.field} ${op} [${vals}]`;
  }
  if (['==', '!=', '>', '<', '>=', '<='].includes(op)) {
    return `${node.field} ${op} ${formatLiteral(node.value)}`;
  }
  return '';
}

function formatLiteral(v: unknown): string {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'string') return JSON.stringify(v);
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  return JSON.stringify(v);
}
