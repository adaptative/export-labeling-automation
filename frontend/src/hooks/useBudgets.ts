import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authFetch } from '@/api/authInterceptor';

const API = '/api/v1';

export interface SpendingTier {
  id: string;
  name: string;
  current_spend: number;
  cap: number;
  unit: string;
  trend_pct: number;
  breaker_active: boolean;
}

export interface BreakerEvent {
  id: string;
  timestamp: string;
  tier: string;
  event_type: string;
  triggered_by: string;
  action: string;
  status: string;
}

export function useCurrentSpend() {
  return useQuery({
    queryKey: ['budgets', 'current-spend'],
    queryFn: async () => {
      const resp = await authFetch(`${API}/budgets/current-spend`);
      if (!resp.ok) throw new Error('Failed to load spending data');
      const data = await resp.json();
      return data.tiers as SpendingTier[];
    },
  });
}

export function useBudgetEvents(filters?: { tier?: string; limit?: number }) {
  return useQuery({
    queryKey: ['budgets', 'events', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.tier) params.set('tier', filters.tier);
      if (filters?.limit) params.set('limit', String(filters.limit));
      const qs = params.toString();
      const resp = await authFetch(`${API}/budgets/events${qs ? `?${qs}` : ''}`);
      if (!resp.ok) throw new Error('Failed to load breaker events');
      return resp.json() as Promise<{ events: BreakerEvent[]; total: number }>;
    },
  });
}

export function useUpdateBudgetCap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { tenantId: string; tier: string; new_cap: number; reason: string }) => {
      const resp = await authFetch(`${API}/budgets/tenant/${body.tenantId}/caps`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tier: body.tier, new_cap: body.new_cap, reason: body.reason }),
      });
      if (!resp.ok) throw new Error('Failed to update cap');
      return resp.json();
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['budgets'] });
    },
  });
}
