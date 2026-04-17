import { useQuery } from '@tanstack/react-query';
import { authFetch } from '@/api/authInterceptor';

const API = '/api/v1';

export interface Artifact {
  artifact_id: string;
  artifact_type: string;
  content_hash: string;
  llm_snapshot?: { model_id: string; prompt_hash: string } | null;
  frozen_inputs: { profile_version?: number; rules_snapshot_id?: string };
  created_at: string;
}

export interface ArtifactDetail extends Artifact {
  size_bytes: number;
  mime_type: string;
  storage_key: string;
  order_id?: string | null;
  created_by?: string | null;
}

export interface ProvenanceStep {
  step_number: number;
  agent_id: string;
  model_id?: string | null;
  prompt_hash?: string | null;
  input_hash: string;
  output_hash: string;
  action: string;
  timestamp: string;
  duration_ms: number;
}

export interface ArtifactFilters {
  search?: string;
  artifact_type?: string;
  order_id?: string;
  limit?: number;
  offset?: number;
}

export function useArtifacts(filters?: ArtifactFilters) {
  return useQuery({
    queryKey: ['artifacts', filters],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters?.search) params.set('search', filters.search);
      if (filters?.artifact_type) params.set('artifact_type', filters.artifact_type);
      if (filters?.order_id) params.set('order_id', filters.order_id);
      if (filters?.limit) params.set('limit', String(filters.limit));
      if (filters?.offset) params.set('offset', String(filters.offset));
      const qs = params.toString();
      const resp = await authFetch(`${API}/artifacts${qs ? `?${qs}` : ''}`);
      if (!resp.ok) throw new Error('Failed to load artifacts');
      return resp.json() as Promise<{ artifacts: Artifact[]; total: number }>;
    },
  });
}

export function useArtifact(artifactId: string | null) {
  return useQuery({
    queryKey: ['artifacts', artifactId],
    queryFn: async () => {
      const resp = await authFetch(`${API}/artifacts/${artifactId}`);
      if (!resp.ok) throw new Error('Failed to load artifact');
      return resp.json() as Promise<ArtifactDetail>;
    },
    enabled: !!artifactId,
  });
}

export function useArtifactProvenance(artifactId: string | null) {
  return useQuery({
    queryKey: ['artifacts', artifactId, 'provenance'],
    queryFn: async () => {
      const resp = await authFetch(`${API}/artifacts/${artifactId}/provenance`);
      if (!resp.ok) throw new Error('Failed to load provenance');
      return resp.json() as Promise<{ artifact_id: string; steps: ProvenanceStep[] }>;
    },
    enabled: !!artifactId,
  });
}
