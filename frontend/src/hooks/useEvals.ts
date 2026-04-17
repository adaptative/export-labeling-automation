/**
 * React-Query hooks for Prompt Evals (INT-013 · Sprint-16).
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  listEvals,
  getEval,
  runAllEvals,
  getRunAllStatus,
  type EvalListResponse,
  type EvalResult,
  type RunAllResponse,
  type RunAllStatus,
} from '@/api/evals';

export function useEvals(agentId?: string) {
  return useQuery<EvalListResponse>({
    queryKey: ['evals', agentId ?? 'all'],
    queryFn: () => listEvals(agentId),
  });
}

export function useEval(evalId: string | null | undefined) {
  return useQuery<EvalResult>({
    queryKey: ['evals', 'detail', evalId],
    enabled: !!evalId,
    queryFn: () => getEval(evalId as string),
  });
}

export function useRunAllEvals() {
  const qc = useQueryClient();
  return useMutation<RunAllResponse>({
    mutationFn: () => runAllEvals(),
    onSuccess: () => {
      // Soft-invalidate the eval list; progress polling runs separately.
      qc.invalidateQueries({ queryKey: ['evals'] });
    },
  });
}

/**
 * Poll the run-all batch status every 2s until it reaches a terminal
 * state. Returns ``null`` when ``batchId`` is falsy.
 */
export function useRunAllStatus(batchId: string | null | undefined) {
  return useQuery<RunAllStatus>({
    queryKey: ['evals', 'run-all', batchId],
    enabled: !!batchId,
    queryFn: () => getRunAllStatus(batchId as string),
    refetchInterval: (query) => {
      const data = query.state.data as RunAllStatus | undefined;
      if (!data) return 2_000;
      return data.status === 'completed' || data.status === 'failed' ? false : 2_000;
    },
  });
}
