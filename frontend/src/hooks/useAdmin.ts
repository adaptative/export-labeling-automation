import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authFetch } from '@/api/authInterceptor';

const API = '/api/v1';

export interface AdminUser {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  status: string;
  last_active: string | null;
  created_at: string;
}

export interface SSOConfig {
  oidc_google_enabled: boolean;
  oidc_google_client_id: string | null;
  saml_microsoft_enabled: boolean;
  saml_microsoft_entity_id: string | null;
}

export function useAdminUsers(filters?: { role?: string; status?: string }) {
  return useQuery({
    queryKey: ['admin', 'users', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.role) params.set('role', filters.role);
      if (filters?.status) params.set('status', filters.status);
      const qs = params.toString();
      const resp = await authFetch(`${API}/admin/users${qs ? `?${qs}` : ''}`);
      if (!resp.ok) throw new Error('Failed to load users');
      const data = await resp.json();
      return data as { users: AdminUser[]; total: number };
    },
  });
}

export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { email: string; display_name: string; role: string }) => {
      const resp = await authFetch(`${API}/admin/users/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed' }));
        throw new Error(err.detail || 'Invite failed');
      }
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useUpdateRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ userId, role }: { userId: string; role: string }) => {
      const resp = await authFetch(`${API}/admin/users/${userId}/role`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role }),
      });
      if (!resp.ok) throw new Error('Failed to update role');
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      const resp = await authFetch(`${API}/admin/users/${userId}/deactivate`, { method: 'POST' });
      if (!resp.ok) throw new Error('Failed to deactivate user');
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useActivateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      const resp = await authFetch(`${API}/admin/users/${userId}/activate`, { method: 'POST' });
      if (!resp.ok) throw new Error('Failed to activate user');
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'users'] }),
  });
}

export function useSSOConfig() {
  return useQuery({
    queryKey: ['admin', 'sso'],
    queryFn: async () => {
      const resp = await authFetch(`${API}/admin/sso`);
      if (!resp.ok) throw new Error('Failed to load SSO config');
      return resp.json() as Promise<SSOConfig>;
    },
  });
}

export function useUpdateSSO() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<SSOConfig & { oidc_google_client_secret?: string; saml_microsoft_metadata_url?: string }>) => {
      const resp = await authFetch(`${API}/admin/sso`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error('Failed to update SSO config');
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin', 'sso'] }),
  });
}
