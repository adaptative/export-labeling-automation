/**
 * Prompt Eval detail view (INT-013 · Sprint-16).
 *
 * Renders the full metrics payload + confusion matrix for a single
 * ``EvalResult``, fetched via ``GET /api/v1/evals/{id}``.
 */
import { useRoute, useLocation } from 'wouter';
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle, Loader2 } from 'lucide-react';

import { useEval } from '@/hooks/useEvals';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import type { EvalStatus } from '@/api/evals';

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
  return (n * 100).toFixed(2) + '%';
}

function formatCostDelta(pct: number): string {
  const sign = pct >= 0 ? '+' : '';
  return `${sign}${pct.toFixed(2)}%`;
}

function formatTimestamp(seconds: number): string {
  return new Date(seconds * 1000).toLocaleString();
}

export default function EvalsDetail() {
  const [, params] = useRoute('/evals/:id');
  const [, setLocation] = useLocation();
  const evalId = params?.id;
  const { data, isLoading, error } = useEval(evalId);

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => setLocation('/evals')}>
          <ArrowLeft className="h-4 w-4 mr-1" /> Back to Evals
        </Button>
      </div>

      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-10 w-1/3" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Failed to load eval: {(error as Error).message}
        </div>
      )}

      {data && (
        <>
          <div className="flex items-start justify-between gap-4 flex-wrap">
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                {data.agent_name}
              </h1>
              <p className="text-sm text-muted-foreground font-mono">
                {data.agent_id} · eval {data.id}
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Ran at {formatTimestamp(data.eval_date)}
                {data.batch_id && ` · batch ${data.batch_id}`}
              </p>
            </div>
            <div>{statusBadge(data.status)}</div>
          </div>

          {data.notes && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Notes</CardTitle>
              </CardHeader>
              <CardContent className="text-sm">{data.notes}</CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card data-testid="card-metrics">
              <CardHeader>
                <CardTitle className="text-base">Metrics</CardTitle>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-2 gap-y-4 gap-x-6">
                  <MetricEntry label="Precision" value={formatPct(data.metrics.precision)} />
                  <MetricEntry label="Recall" value={formatPct(data.metrics.recall)} />
                  <MetricEntry label="F1 Score" value={formatPct(data.metrics.f1_score)} />
                  <MetricEntry label="Accuracy" value={formatPct(data.metrics.accuracy)} />
                  <MetricEntry
                    label="Cost Delta"
                    value={formatCostDelta(data.metrics.cost_delta)}
                    valueClass={
                      data.metrics.cost_delta < 0
                        ? 'text-green-600'
                        : data.metrics.cost_delta > 0
                        ? 'text-red-600'
                        : ''
                    }
                  />
                  <MetricEntry
                    label="Sample Size"
                    value={data.metrics.sample_size.toLocaleString()}
                  />
                </dl>
              </CardContent>
            </Card>

            {data.confusion && (
              <Card data-testid="card-confusion">
                <CardHeader>
                  <CardTitle className="text-base">Confusion Matrix</CardTitle>
                </CardHeader>
                <CardContent>
                  <ConfusionMatrixGrid matrix={data.confusion} />
                </CardContent>
              </Card>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function MetricEntry({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={`font-mono text-base font-semibold ${valueClass ?? ''}`}>
        {value}
      </dd>
    </div>
  );
}

function ConfusionMatrixGrid({
  matrix,
}: {
  matrix: {
    true_positive: number;
    false_positive: number;
    true_negative: number;
    false_negative: number;
  };
}) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 text-xs text-center">
        <div />
        <div className="font-semibold text-muted-foreground">Predicted +</div>
        <div className="font-semibold text-muted-foreground">Predicted -</div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="flex items-center justify-end text-xs font-semibold text-muted-foreground pr-2">
          Actual +
        </div>
        <MatrixCell label="TP" value={matrix.true_positive} tone="good" />
        <MatrixCell label="FN" value={matrix.false_negative} tone="bad" />
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="flex items-center justify-end text-xs font-semibold text-muted-foreground pr-2">
          Actual -
        </div>
        <MatrixCell label="FP" value={matrix.false_positive} tone="bad" />
        <MatrixCell label="TN" value={matrix.true_negative} tone="good" />
      </div>
    </div>
  );
}

function MatrixCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: 'good' | 'bad';
}) {
  const palette =
    tone === 'good'
      ? 'bg-green-50 border-green-200 text-green-800'
      : 'bg-red-50 border-red-200 text-red-800';
  return (
    <div className={`rounded-md border px-4 py-3 ${palette}`}>
      <div className="text-xs font-semibold opacity-80">{label}</div>
      <div className="text-2xl font-bold font-mono">{value.toLocaleString()}</div>
    </div>
  );
}
