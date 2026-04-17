import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { authFetch } from '@/api/authInterceptor';

const API = '/api/v1';

export interface Profile {
  user_id: string;
  email: string;
  display_name: string;
  phone: string | null;
  timezone: string;
  language: string;
}

export interface MFAStatus {
  enabled: boolean;
  method: string | null;
}

export function useProfile() {
  return useQuery({
    queryKey: ['settings', 'profile'],
    queryFn: async () => {
      const resp = await authFetch(`${API}/settings/profile`);
      if (!resp.ok) throw new Error('Failed to load profile');
      return resp.json() as Promise<Profile>;
    },
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Partial<Omit<Profile, 'user_id' | 'email'>>) => {
      const resp = await authFetch(`${API}/settings/profile`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) throw new Error('Failed to update profile');
      return resp.json() as Promise<Profile>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'profile'] }),
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: async (body: { current_password: string; new_password: string }) => {
      const resp = await authFetch(`${API}/settings/password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed' }));
        throw new Error(err.detail || 'Password change failed');
      }
      return resp.json();
    },
  });
}

export function useMFAStatus() {
  return useQuery({
    queryKey: ['settings', 'mfa'],
    queryFn: async () => {
      const resp = await authFetch(`${API}/settings/mfa`);
      if (!resp.ok) throw new Error('Failed to load MFA status');
      return resp.json() as Promise<MFAStatus>;
    },
  });
}

export function useEnableMFA() {
  return useMutation({
    mutationFn: async (method: string = 'totp') => {
      const resp = await authFetch(`${API}/settings/mfa/enable`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ method }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed' }));
        throw new Error(err.detail || 'MFA setup failed');
      }
      return resp.json() as Promise<{ secret: string; qr_uri: string; message: string }>;
    },
  });
}

export function useVerifyMFA() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (code: string) => {
      const resp = await authFetch(`${API}/settings/mfa/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Invalid code' }));
        throw new Error(err.detail || 'Verification failed');
      }
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'mfa'] }),
  });
}

export function useDisableMFA() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const resp = await authFetch(`${API}/settings/mfa/disable`, { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Failed' }));
        throw new Error(err.detail || 'MFA disable failed');
      }
      return resp.json();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'mfa'] }),
  });
}
