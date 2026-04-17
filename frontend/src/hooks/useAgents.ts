/**
 * React-Query hooks for the Agent Inspector (INT-013 · Sprint-16).
 */
import { useQuery } from '@tanstack/react-query';

import { listAgents, getAgent, type AgentListResponse, type AgentCard } from '@/api/agents';

export function useAgents() {
  return useQuery<AgentListResponse>({
    queryKey: ['agents'],
    queryFn: () => listAgents(),
    // Refresh every 30s so the "idle → healthy → degraded" status flicks
    // promptly when background agents run.
    refetchInterval: 30_000,
  });
}

export function useAgent(agentId: string | null | undefined) {
  return useQuery<AgentCard>({
    queryKey: ['agents', agentId],
    enabled: !!agentId,
    queryFn: () => getAgent(agentId as string),
  });
}
