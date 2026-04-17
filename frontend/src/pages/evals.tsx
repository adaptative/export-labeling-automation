/**
 * Prompt Evals dashboard (INT-013 · Sprint-16).
 *
 * Lists the latest eval result per agent, with an agent-id filter
 * dropdown, a "Run All Evals" button that triggers a batch on the
 * backend, and a progress bar that polls every 2s until the batch
 * reaches a terminal state. Clicking a row routes to ``/evals/:id``.
 */
import { useMemo, useState } from 'react';
import { useLocation } from 'wouter';
import { CheckCircle2, XCircle, AlertTriangle, Loader2, Play } from 'lucide-react';

import { useEvals, useRunAllEvals, useRunAllStatus } from '@/hooks/useEvals';
import { useAgents } from '@/hooks/useAgents';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { EvalStatus, EvalResult } from '@/api/evals';

const ALL = '__ALL__';

function statusBadge(status: EvalStatus) {
  switch (status) {
    case 'pass':
      return (
        <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200 gap-1">
          <CheckCircle2 className="h-3 w-3" /> pass
        </Badge>
      );
    case 'fail':
      return (
        <Badge variant="destructive" className="gap-1">
          <XCircle className="h-3 w-3" /> fail
        </Badge>
      );
    case 'warn':
      return (
        <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 gap-1">
          <AlertTriangle className="h-3 w-3" /> warn
        </Badge>
      );
    default:
      return (
        <Badge variant="outline" className="gap-1">
          <Loader2 className="h-3 w-3 animate-spin" /> running
        </Badge>
      );
  }
}

function formatPct(n: number): string {
  return (n * 100).toFixed(1) + '%';
}

function formatCostDelta(pct: number): string {
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(1)}%`;
}

function costDeltaColour(pct: number): string {
  if (pct < 0) return 'text-green-600';
  if (pct > 0) return 'text-red-600';
  return 'text-muted-foreground';
}

function relativeDate(seconds: number): string {
  const delta = (Date.now() - seconds * 1000) / 1000;
  if (delta < 60) return `${Math.floor(delta)}s ago`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

export default function Evals() {
  const [, setLocation] = useLocation();
  const [agentFilter, setAgentFilter] = useState<string>(ALL);
  const [batchId, setBatchId] = useState<string | null>(null);

  const { data: agentsData } = useAgents();
  const { data, isLoading, error, refetch } = useEvals(
    agentFilter === ALL ? undefined : agentFilter,
  );
  const runAll = useRunAllEvals();
  const { data: batchStatus } = useRunAllStatus(batchId);

  // When the batch completes, refresh the eval list and clear the batch
  // after a short grace period so the progress bar lingers briefly.
  const batchTerminal =
    batchStatus?.status === 'completed' || batchStatus?.status === 'failed';

  const handleRunAll = async () => {
    const res = await runAll.mutateAsync();
    setBatchId(res.eval_batch_id);
  };

  const handleClearBatch = () => {
    setBatchId(null);
    refetch();
  };

  const counts = useMemo(() => {
    const evals = data?.evals ?? [];
    return {
      pass: evals.filter((e) => e.status === 'pass').length,
      warn: evals.filter((e) => e.status === 'warn').length,
      fail: evals.filter((e) => e.status === 'fail').length,
      running: evals.filter((e) => e.status === 'running').length,
    };
  }, [data]);

  const progress = batchStatus
    ? Math.round(
        ((batchStatus.completed + batchStatus.failed) /
          Math.max(batchStatus.total, 1)) *
          100,
      )
    : 0;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Prompt Evals</h1>
          <p className="text-sm text-muted-foreground">
            Continuous integration suite across all LLM-backed agents.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={agentFilter} onValueChange={setAgentFilter}>
            <SelectTrigger className="w-[220px]" data-testid="select-agent-filter">
              <SelectValue placeholder="All agents" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>All agents</SelectItem>
              {agentsData?.agents.map((a) => (
                <SelectItem key={a.agent_id} value={a.agent_id}>
                  {a.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            onClick={handleRunAll}
            disabled={runAll.isPending || (!!batchId && !batchTerminal)}
            data-testid="button-run-all"
          >
            {runAll.isPending || (!!batchId && !batchTerminal) ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" /> Running…
              </>
            ) : (
              <>
                <Play className="h-4 w-4 mr-2" /> Run All Evals
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Summary chips */}
      <div className="flex gap-3 text-sm flex-wrap">
        <SummaryChip label="Pass" value={counts.pass} tone="pass" />
        <SummaryChip label="Warn" value={counts.warn} tone="warn" />
        <SummaryChip label="Fail" value={counts.fail} tone="fail" />
        {counts.running > 0 && (
          <SummaryChip label="Running" value={counts.running} tone="default" />
        )}
      </div>

      {/* Run-all progress */}
      {batchId && batchStatus && (
        <Card data-testid="card-run-all-progress">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">
                Batch {batchStatus.eval_batch_id}
              </CardTitle>
              <Badge
                variant={
                  batchStatus.status === 'failed' ? 'destructive' : 'outline'
                }
                className={
                  batchStatus.status === 'completed'
                    ? 'bg-green-50 text-green-700 border-green-200'
                    : ''
                }
              >
                {batchStatus.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <Progress value={progress} />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {batchStatus.completed + batchStatus.failed} / {batchStatus.total}{' '}
                complete · {batchStatus.failed} failed
              </span>
              {batchTerminal && (
                <Button variant="ghost" size="sm" onClick={handleClearBatch}>
                  Dismiss
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Failed to load evals: {(error as Error).message}
        </div>
      )}

      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Precision</TableHead>
                <TableHead className="text-right">Recall</TableHead>
                <TableHead className="text-right">F1</TableHead>
                <TableHead className="text-right">Accuracy</TableHead>
                <TableHead className="text-right">Cost Δ</TableHead>
                <TableHead className="text-right">Samples</TableHead>
                <TableHead>Run</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading &&
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={`skel-${i}`}>
                    {Array.from({ length: 9 }).map((__, j) => (
                      <TableCell key={j}>
                        <Skeleton className="h-4 w-full" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              {data?.evals.map((ev) => (
                <EvalRow
                  key={ev.id}
                  ev={ev}
                  onOpen={() => setLocation(`/evals/${ev.id}`)}
                />
              ))}
              {!isLoading && (data?.evals.length ?? 0) === 0 && (
                <TableRow>
                  <TableCell colSpan={9} className="text-center text-muted-foreground py-8">
                    No eval results yet. Click <b>Run All Evals</b> to seed a batch.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

function EvalRow({ ev, onOpen }: { ev: EvalResult; onOpen: () => void }) {
  return (
    <TableRow
      className="cursor-pointer hover:bg-muted/50"
      onClick={onOpen}
      data-testid={`row-eval-${ev.id}`}
    >
      <TableCell>
        <div className="font-medium">{ev.agent_name}</div>
        <div className="text-xs text-muted-foreground font-mono">{ev.agent_id}</div>
      </TableCell>
      <TableCell>{statusBadge(ev.status)}</TableCell>
      <TableCell className="text-right font-mono">
        {formatPct(ev.metrics.precision)}
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatPct(ev.metrics.recall)}
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatPct(ev.metrics.f1_score)}
      </TableCell>
      <TableCell className="text-right font-mono">
        {formatPct(ev.metrics.accuracy)}
      </TableCell>
      <TableCell
        className={`text-right font-mono ${costDeltaColour(ev.metrics.cost_delta)}`}
      >
        {formatCostDelta(ev.metrics.cost_delta)}
      </TableCell>
      <TableCell className="text-right font-mono">
        {ev.metrics.sample_size.toLocaleString()}
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {relativeDate(ev.eval_date)}
      </TableCell>
    </TableRow>
  );
}

function SummaryChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'pass' | 'warn' | 'fail' | 'default';
}) {
  const palette: Record<typeof tone, string> = {
    pass: 'border-green-200 bg-green-50 text-green-800',
    warn: 'border-amber-200 bg-amber-50 text-amber-800',
    fail: 'border-red-200 bg-red-50 text-red-800',
    default: '',
  };
  return (
    <div
      className={`flex items-center gap-2 rounded-md border px-3 py-1.5 ${palette[tone]}`}
    >
      <div className="text-xs">
        <div className="font-medium">{label}</div>
        <div className="font-semibold text-sm">{value}</div>
      </div>
    </div>
  );
}
