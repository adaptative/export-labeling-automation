/**
 * Agent Inspector (INT-013 · Sprint-16).
 *
 * Renders the 14 Labelforge agents as cards, each backed by live
 * telemetry from ``/api/v1/agents``. Status dot colour keys off the
 * backend-computed status ("healthy" | "degraded" | "idle"). Clicking a
 * card navigates to ``/agents/:id`` (detail view reserved for INT-021).
 */
import { useMemo } from 'react';
import { useLocation } from 'wouter';
import { Activity, AlertTriangle, Bot, Loader2 } from 'lucide-react';

import { useAgents } from '@/hooks/useAgents';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import type { AgentCard as AgentCardType, AgentStatus } from '@/api/agents';

function statusColour(status: AgentStatus): string {
  switch (status) {
    case 'healthy':
      return 'bg-green-500';
    case 'degraded':
      return 'bg-red-500';
    default:
      return 'bg-slate-300';
  }
}

function formatRelative(seconds: number | null | undefined): string {
  if (!seconds) return 'never';
  const deltaMs = Date.now() - seconds * 1000;
  const secs = Math.floor(deltaMs / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function Agents() {
  const [, setLocation] = useLocation();
  const { data, isLoading, error } = useAgents();

  const { totalCalls, avgLatency, totalCost, degraded } = useMemo(() => {
    const agents = data?.agents ?? [];
    const totalCalls = agents.reduce((n, a) => n + a.calls, 0);
    const weighted =
      totalCalls > 0
        ? agents.reduce((s, a) => s + a.avg_latency_ms * a.calls, 0) / totalCalls
        : 0;
    const totalCost = agents.reduce((s, a) => s + a.total_cost_usd, 0);
    const degraded = agents.filter((a) => a.status === 'degraded').length;
    return { totalCalls, avgLatency: weighted, totalCost, degraded };
  }, [data]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Agent Inspector</h1>
          <p className="text-sm text-muted-foreground">
            Live telemetry for the 14 Labelforge agents.
          </p>
        </div>
        {data && (
          <div className="flex gap-4 text-sm">
            <StatChip icon={<Bot className="h-4 w-4" />} label="Agents" value={String(data.total)} />
            <StatChip
              icon={<Activity className="h-4 w-4" />}
              label="Calls (cumulative)"
              value={totalCalls.toLocaleString()}
            />
            <StatChip
              icon={<Activity className="h-4 w-4" />}
              label="Avg latency"
              value={`${avgLatency.toFixed(0)} ms`}
            />
            <StatChip
              icon={<Activity className="h-4 w-4" />}
              label="Cost"
              value={`$${totalCost.toFixed(2)}`}
            />
            {degraded > 0 && (
              <StatChip
                icon={<AlertTriangle className="h-4 w-4 text-red-500" />}
                label="Degraded"
                value={String(degraded)}
                tone="danger"
              />
            )}
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Failed to load agents: {(error as Error).message}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {isLoading &&
          Array.from({ length: 8 }).map((_, i) => (
            <Card key={`skel-${i}`}>
              <CardHeader>
                <Skeleton className="h-5 w-40" />
              </CardHeader>
              <CardContent>
                <Skeleton className="h-20 w-full" />
              </CardContent>
            </Card>
          ))}

        {data?.agents.map((agent) => (
          <AgentTile
            key={agent.agent_id}
            agent={agent}
            onOpen={() => setLocation(`/agents/${agent.agent_id}`)}
          />
        ))}
      </div>
    </div>
  );
}

function AgentTile({
  agent,
  onOpen,
}: {
  agent: AgentCardType;
  onOpen: () => void;
}) {
  const successPct = (agent.success_rate * 100).toFixed(1);
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen();
        }
      }}
      className="cursor-pointer hover:border-primary transition-colors"
      data-testid={`card-agent-${agent.agent_id}`}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{agent.name}</CardTitle>
          <div
            className={`w-2 h-2 rounded-full ${statusColour(agent.status)}`}
            title={agent.status}
            aria-label={`status: ${agent.status}`}
          />
        </div>
        <div className="flex items-center gap-2 mt-1">
          <Badge variant="secondary" className="font-mono text-xs">
            {agent.kind}
          </Badge>
          <span className="text-xs text-muted-foreground font-mono truncate">
            {agent.agent_id}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 mt-2">
          <div>
            <div className="text-xs text-muted-foreground">Calls</div>
            <div className="font-medium">{agent.calls.toLocaleString()}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Success rate</div>
            <div
              className={`font-medium ${
                agent.status === 'degraded' ? 'text-red-600' : 'text-green-600'
              }`}
            >
              {agent.calls === 0 ? '—' : `${successPct}%`}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Avg latency</div>
            <div className="font-medium">
              {agent.calls === 0 ? '—' : `${agent.avg_latency_ms.toFixed(0)} ms`}
            </div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground">Cost</div>
            <div className="font-medium">${agent.total_cost_usd.toFixed(4)}</div>
          </div>
          <div className="col-span-2">
            <div className="text-xs text-muted-foreground">Last call</div>
            <div className="font-medium text-xs">{formatRelative(agent.last_call_at)}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatChip({
  icon,
  label,
  value,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: 'default' | 'danger';
}) {
  return (
    <div
      className={`flex items-center gap-2 rounded-md border px-3 py-1.5 ${
        tone === 'danger' ? 'border-red-200 bg-red-50' : ''
      }`}
    >
      {icon}
      <div className="text-xs">
        <div className="text-muted-foreground">{label}</div>
        <div className="font-semibold text-sm">{value}</div>
      </div>
    </div>
  );
}
