import { useQuery } from '@tanstack/react-query';
import { authFetch } from '@/api/authInterceptor';

const API = '/api/v1';

export interface AuditEntry {
  id: string;
  timestamp: string;
  actor: string;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: string;
  ip_address: string;
  metadata?: Record<string, unknown> | null;
}

export interface AuditFilters {
  search?: string;
  actor_type?: string;
  action?: string;
  sort_order?: string;
  limit?: number;
  offset?: number;
}

export function useAuditLog(filters?: AuditFilters) {
  return useQuery({
    queryKey: ['audit-log', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.search) params.set('search', filters.search);
      if (filters?.actor_type) params.set('actor_type', filters.actor_type);
      if (filters?.action) params.set('action', filters.action);
      if (filters?.sort_order) params.set('sort_order', filters.sort_order);
      if (filters?.limit) params.set('limit', String(filters.limit));
      if (filters?.offset) params.set('offset', String(filters.offset));
      const qs = params.toString();
      const resp = await authFetch(`${API}/audit-log${qs ? `?${qs}` : ''}`);
      if (!resp.ok) throw new Error('Failed to load audit log');
      return resp.json() as Promise<{ entries: AuditEntry[]; total: number; limit: number; offset: number }>;
    },
  });
}

export function useAuditEntry(entryId: string | null) {
  return useQuery({
    queryKey: ['audit-log', entryId],
    queryFn: async () => {
      const resp = await authFetch(`${API}/audit-log/${entryId}`);
      if (!resp.ok) throw new Error('Failed to load audit entry');
      return resp.json() as Promise<AuditEntry>;
    },
    enabled: !!entryId,
  });
}
