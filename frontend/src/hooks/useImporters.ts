/**
 * Importer + onboarding hooks (Sprint 8).
 *
 * Thin wrappers around `/api/v1/importers/*` that match the rest of the
 * project's `useQuery` / `useMutation` conventions.  Pages can still call
 * `apiGet` directly — these hooks are for new call sites that want cache
 * invalidation and retry handling.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { apiDelete, apiGet, apiPost, apiPut, apiUpload } from '@/api/authInterceptor';

/* ── Types ────────────────────────────────────────────────────────────── */

export interface ImporterProfile {
  importer_id: string;
  name?: string | null;
  code?: string | null;
  brand_treatment?: Record<string, unknown> | null;
  panel_layouts?: Record<string, unknown> | null;
  handling_symbol_rules?: Record<string, unknown> | null;
  pi_template_mapping?: Record<string, unknown> | null;
  logo_asset_hash?: string | null;
  version: number;
}

export interface ImporterListResponse {
  importers: ImporterProfile[];
  total: number;
}

export interface ImporterDocument {
  id: string;
  doc_type: string;
  filename: string;
  size_bytes: number | null;
  version: number;
  uploaded_at: string;
  content_hash?: string | null;
}

export interface ImporterOrderItem {
  id: string;
  po_number: string | null;
  external_ref: string | null;
  created_at: string;
}

export interface OnboardingAgentStatus {
  status: 'pending' | 'running' | 'completed' | 'failed';
  confidence?: number | null;
  error?: string | null;
  needs_hitl?: boolean;
}

export interface OnboardingExtractionResponse {
  session_id: string;
  status: 'in_progress' | 'ready_for_review' | 'completed' | 'failed';
  agents: Record<string, OnboardingAgentStatus>;
  extracted_values: Record<string, unknown> | null;
  started_at: string;
  completed_at: string | null;
}

/* ── Queries ──────────────────────────────────────────────────────────── */

export function useImporters(filters?: { search?: string; includeInactive?: boolean }) {
  return useQuery({
    queryKey: ['importers', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.search) params.set('search', filters.search);
      if (filters?.includeInactive) params.set('include_inactive', 'true');
      const qs = params.toString();
      return apiGet<ImporterListResponse>(`/importers${qs ? `?${qs}` : ''}`);
    },
  });
}

export function useImporter(importerId: string | null | undefined) {
  return useQuery({
    queryKey: ['importers', importerId],
    enabled: !!importerId,
    queryFn: () => apiGet<ImporterProfile>(`/importers/${importerId}`),
  });
}

export function useImporterDocuments(importerId: string | null | undefined) {
  return useQuery({
    queryKey: ['importers', importerId, 'documents'],
    enabled: !!importerId,
    queryFn: () =>
      apiGet<{ documents: ImporterDocument[]; total: number }>(
        `/importers/${importerId}/documents`,
      ),
  });
}

export function useImporterOrders(importerId: string | null | undefined) {
  return useQuery({
    queryKey: ['importers', importerId, 'orders'],
    enabled: !!importerId,
    queryFn: () =>
      apiGet<{ orders: ImporterOrderItem[]; total: number }>(
        `/importers/${importerId}/orders`,
      ),
  });
}

export function useImporterHiTL(importerId: string | null | undefined) {
  return useQuery({
    queryKey: ['importers', importerId, 'hitl'],
    enabled: !!importerId,
    queryFn: () =>
      apiGet<{ threads: Array<Record<string, unknown>>; total: number }>(
        `/importers/${importerId}/hitl-threads`,
      ),
  });
}

export function useImporterRules(importerId: string | null | undefined) {
  return useQuery({
    queryKey: ['importers', importerId, 'rules'],
    enabled: !!importerId,
    queryFn: () =>
      apiGet<{ rules: Array<Record<string, unknown>>; total: number }>(
        `/importers/${importerId}/rules`,
      ),
  });
}

/* ── Mutations ────────────────────────────────────────────────────────── */

export function useCreateImporter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; code?: string; contact_email?: string; contact_phone?: string; address?: string }) =>
      apiPost<{ id: string; name: string; code: string }>(`/importers`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['importers'] });
    },
  });
}

export function useUpdateImporter(importerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<ImporterProfile> & { name?: string; is_active?: boolean }) =>
      apiPut<ImporterProfile>(`/importers/${importerId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['importers'] });
      qc.invalidateQueries({ queryKey: ['importers', importerId] });
    },
  });
}

export function useDeleteImporter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (importerId: string) => apiDelete(`/importers/${importerId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['importers'] });
    },
  });
}

export function useUploadImporterDocument(importerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { docType: string; file: File }) => {
      const fd = new globalThis.FormData();
      fd.append('file', input.file);
      return apiUpload<ImporterDocument>(
        `/importers/${importerId}/documents/${input.docType}`,
        fd,
      );
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['importers', importerId, 'documents'] });
    },
  });
}

export function useDeleteImporterDocument(importerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (docType: string) =>
      apiDelete(`/importers/${importerId}/documents/${docType}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['importers', importerId, 'documents'] });
    },
  });
}

export function useRequestDocumentFromBuyer(importerId: string) {
  return useMutation({
    mutationFn: (docType: string) =>
      apiPost<{ notification_id: string }>(
        `/importers/${importerId}/documents/${docType}/request-from-buyer`,
      ),
  });
}

/* ── Onboarding ───────────────────────────────────────────────────────── */

export function useStartOnboarding() {
  return useMutation({
    mutationFn: (importerId: string) =>
      apiPost<{ session_id: string; status: string }>(
        `/importers/${importerId}/onboarding/start`,
      ),
  });
}

export function useUploadOnboardingDocs(importerId: string) {
  return useMutation({
    mutationFn: async (files: File[]) => {
      const fd = new globalThis.FormData();
      files.forEach((f) => fd.append('files', f));
      return apiUpload<{ session_id: string; status: string; uploaded_docs: string[] }>(
        `/importers/${importerId}/onboarding/upload`,
        fd,
      );
    },
  });
}

/**
 * Poll the onboarding extraction endpoint every `intervalMs` while the
 * session is still `in_progress`. Stops when status is terminal or the
 * polling budget elapses.
 */
export function useOnboardingExtraction(
  importerId: string | null | undefined,
  options?: { enabled?: boolean; intervalMs?: number },
) {
  const interval = options?.intervalMs ?? 2000;
  return useQuery({
    queryKey: ['importers', importerId, 'onboarding-extraction'],
    enabled: options?.enabled !== false && !!importerId,
    refetchInterval: (query) => {
      const data = query.state.data as OnboardingExtractionResponse | undefined;
      if (!data) return interval;
      if (data.status === 'in_progress') return interval;
      return false;
    },
    queryFn: () =>
      apiGet<OnboardingExtractionResponse>(
        `/importers/${importerId}/onboarding/extraction`,
      ),
  });
}

export function useFinalizeOnboarding(importerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiPost<{ importer_id: string; profile_version: number }>(
        `/importers/${importerId}/onboard/finalize`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['importers'] });
      qc.invalidateQueries({ queryKey: ['importers', importerId] });
    },
  });
}
