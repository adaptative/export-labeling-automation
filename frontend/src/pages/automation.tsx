/**
 * Automation KPI dashboard (INT-019 · Sprint-16).
 *
 * Consumes ``GET /api/v1/analytics/automation-rate`` and renders:
 *   • KPI cards (current rate, avg rate, best/worst day, trend, top error stage)
 *   • LineChart of daily automation % with a green ReferenceArea marking the
 *     60–85 % target corridor.
 *   • Stacked AreaChart of intake / fusion / compliance error counts.
 *
 * Refreshes silently every 5 minutes via ``useAutomationRate``.
 */
import { useMemo, useState } from 'react';
import {
  TrendingUp,
  TrendingDown,
  Target,
  Award,
  AlertOctagon,
  Activity,
} from 'lucide-react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { useAutomationRate } from '@/hooks/useAutomation';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { AutomationRatePoint } from '@/api/analytics';

type PeriodOption = '7d' | '14d' | '30d' | '90d';

const PERIOD_LABELS: Record<PeriodOption, string> = {
  '7d': 'Last 7 days',
  '14d': 'Last 14 days',
  '30d': 'Last 30 days',
  '90d': 'Last 90 days',
};

function formatDate(d: string): string {
  // d is YYYY-MM-DD — render as "Mar 12".
  const dt = new Date(`${d}T00:00:00Z`);
  return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function formatPct(n: number): string {
  return `${n.toFixed(1)}%`;
}

export default function Automation() {
  const [period, setPeriod] = useState<PeriodOption>('30d');
  const { data, isLoading, error } = useAutomationRate(period);

  const chartData = useMemo(() => {
    if (!data) return [] as Array<AutomationRatePoint & { label: string }>;
    return data.points.map((p) => ({ ...p, label: formatDate(p.date) }));
  }, [data]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between gap-6 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Automation KPIs</h1>
          <p className="text-sm text-muted-foreground">
            Daily automation rate and error breakdown by stage.
          </p>
        </div>
        <Select value={period} onValueChange={(v) => setPeriod(v as PeriodOption)}>
          <SelectTrigger className="w-[180px]" data-testid="select-period">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(PERIOD_LABELS) as PeriodOption[]).map((p) => (
              <SelectItem key={p} value={p}>
                {PERIOD_LABELS[p]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Failed to load analytics: {(error as Error).message}
        </div>
      )}

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading &&
          Array.from({ length: 4 }).map((_, i) => (
            <Card key={`skel-${i}`}>
              <CardContent className="p-5">
                <Skeleton className="h-5 w-20 mb-3" />
                <Skeleton className="h-8 w-24" />
              </CardContent>
            </Card>
          ))}

        {data && (
          <>
            <KpiCard
              label="Current rate"
              value={formatPct(data.summary.current_rate)}
              sub={`Target ${data.summary.target_low}–${data.summary.target_high}%`}
              icon={<Target className="h-4 w-4" />}
              tone={
                data.summary.current_rate >= data.summary.target_low &&
                data.summary.current_rate <= data.summary.target_high
                  ? 'good'
                  : 'warn'
              }
              testId="kpi-current"
            />
            <KpiCard
              label="Average rate"
              value={formatPct(data.summary.average_rate)}
              sub={
                data.summary.trend_pct >= 0
                  ? `▲ ${data.summary.trend_pct.toFixed(1)}% vs prior period`
                  : `▼ ${Math.abs(data.summary.trend_pct).toFixed(1)}% vs prior period`
              }
              icon={
                data.summary.trend_pct >= 0 ? (
                  <TrendingUp className="h-4 w-4" />
                ) : (
                  <TrendingDown className="h-4 w-4" />
                )
              }
              tone={data.summary.trend_pct >= 0 ? 'good' : 'warn'}
              testId="kpi-average"
            />
            <KpiCard
              label="Best day"
              value={
                data.summary.best_day
                  ? formatPct(data.summary.best_day.rate_percent)
                  : '—'
              }
              sub={data.summary.best_day ? formatDate(data.summary.best_day.date) : ''}
              icon={<Award className="h-4 w-4" />}
              tone="good"
              testId="kpi-best"
            />
            <KpiCard
              label="Top error stage"
              value={capitalise(data.summary.top_error_stage)}
              sub={
                data.summary.worst_day
                  ? `Worst ${formatPct(data.summary.worst_day.rate_percent)} on ${formatDate(data.summary.worst_day.date)}`
                  : ''
              }
              icon={<AlertOctagon className="h-4 w-4" />}
              tone={data.summary.top_error_stage === 'none' ? 'default' : 'warn'}
              testId="kpi-top-error"
            />
          </>
        )}
      </div>

      {/* Rate line chart */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="h-4 w-4" /> Daily automation rate
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-72 w-full" />
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 10, right: 24, bottom: 4, left: -8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="label" fontSize={12} tick={{ fill: '#64748b' }} />
                  <YAxis
                    domain={[0, 100]}
                    unit="%"
                    fontSize={12}
                    tick={{ fill: '#64748b' }}
                  />
                  {data && (
                    <ReferenceArea
                      y1={data.summary.target_low}
                      y2={data.summary.target_high}
                      fill="#16a34a"
                      fillOpacity={0.08}
                      strokeOpacity={0}
                      ifOverflow="extendDomain"
                    />
                  )}
                  <Tooltip
                    formatter={(value: number) => [`${value.toFixed(1)}%`, 'Rate']}
                    labelFormatter={(label) => label}
                  />
                  <Line
                    type="monotone"
                    dataKey="rate_percent"
                    stroke="#2563eb"
                    strokeWidth={2}
                    dot={{ r: 2 }}
                    activeDot={{ r: 5 }}
                    name="Automation %"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Error-stage stacked area */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <AlertOctagon className="h-4 w-4" /> Errors by stage
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-72 w-full" />
          ) : (
            <div className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 24, bottom: 4, left: -8 }}>
                  <defs>
                    <linearGradient id="intakeFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0.1} />
                    </linearGradient>
                    <linearGradient id="fusionFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0.1} />
                    </linearGradient>
                    <linearGradient id="complianceFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.6} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0.1} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="label" fontSize={12} tick={{ fill: '#64748b' }} />
                  <YAxis fontSize={12} tick={{ fill: '#64748b' }} allowDecimals={false} />
                  <Tooltip />
                  <Legend />
                  <Area
                    type="monotone"
                    dataKey="intake_errors"
                    stackId="errors"
                    stroke="#f59e0b"
                    fill="url(#intakeFill)"
                    name="Intake"
                  />
                  <Area
                    type="monotone"
                    dataKey="fusion_errors"
                    stackId="errors"
                    stroke="#6366f1"
                    fill="url(#fusionFill)"
                    name="Fusion"
                  />
                  <Area
                    type="monotone"
                    dataKey="compliance_errors"
                    stackId="errors"
                    stroke="#ef4444"
                    fill="url(#complianceFill)"
                    name="Compliance"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function KpiCard({
  label,
  value,
  sub,
  icon,
  tone,
  testId,
}: {
  label: string;
  value: string;
  sub?: string;
  icon?: React.ReactNode;
  tone?: 'good' | 'warn' | 'default';
  testId?: string;
}) {
  const valueClass =
    tone === 'good'
      ? 'text-green-600'
      : tone === 'warn'
      ? 'text-amber-600'
      : '';
  return (
    <Card data-testid={testId}>
      <CardContent className="p-5 space-y-1">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          {icon}
          <span>{label}</span>
        </div>
        <div className={`text-2xl font-bold font-mono ${valueClass}`}>{value}</div>
        {sub && <div className="text-xs text-muted-foreground">{sub}</div>}
      </CardContent>
    </Card>
  );
}

function capitalise(s: string): string {
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1);
}
