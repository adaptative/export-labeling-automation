import React, { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'wouter';
import { apiGet } from '../api/authInterceptor';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, ReferenceArea } from 'recharts';
import {
  Layers, AlertTriangle, CheckCircle2, Loader2, Clock,
  Bot, User, RefreshCw, Pause,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

/* ── Types matching backend DashboardResponse ────────────────────────── */

interface KPICard {
  key: string;
  label: string;
  value: number;
  detail: string;
  trend?: number;
}

interface ActiveOrder {
  id: string;
  po_number: string;
  importer_id: string;
  state: string;
  item_count: number;
  progress: number;
  issues: number;
}

interface ActivityEntry {
  id: string;
  timestamp: string;
  actor: string;
  actor_type: string;
  detail: string;
}

interface AutomationPoint {
  date: string;
  rate: number;
}

interface DashboardResponse {
  kpis: KPICard[];
  active_orders: ActiveOrder[];
  recent_activity: ActivityEntry[];
  automation_series: AutomationPoint[];
}

/* ── KPI icons and formatting ────────────────────────────────────────── */

const KPI_CONFIG: Record<string, { icon: React.ReactNode; format: (v: number) => string; color?: string }> = {
  active_orders:   { icon: <Layers className="w-4 h-4 text-muted-foreground" />,  format: v => String(v) },
  hitl_open:       { icon: <AlertTriangle className="w-4 h-4 text-orange-500" />, format: v => String(v), color: 'text-orange-600' },
  automation_rate: { icon: <CheckCircle2 className="w-4 h-4 text-green-500" />,   format: v => `${v}%`, color: 'text-green-600' },
  today_spend:     { icon: <Clock className="w-4 h-4 text-muted-foreground" />,    format: v => `$${v.toFixed(2)}` },
};

const STATE_DOTS: Record<string, string> = {
  HUMAN_BLOCKED: 'bg-orange-500 animate-pulse',
  READY_TO_DELIVER: 'bg-yellow-500',
  IN_PROGRESS: 'bg-blue-500',
  ATTENTION: 'bg-red-500',
  CREATED: 'bg-gray-400',
};

export default function Dashboard() {
  const [, setLocation] = useLocation();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchDashboard = useCallback(async () => {
    try {
      const resp = await apiGet<DashboardResponse>('/dashboard/stats');
      setData(resp);
      setLastUpdated(new Date());
      setError(null);
    } catch (e: any) {
      setError(e.message || 'Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchDashboard(); }, [fetchDashboard]);

  // Poll every 30 seconds
  useEffect(() => {
    const interval = setInterval(fetchDashboard, 30000);
    return () => clearInterval(interval);
  }, [fetchDashboard]);

  if (loading && !data) {
    return (
      <div className="p-6 flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading dashboard...</span>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="p-6 text-center">
        <p className="text-red-600">{error}</p>
        <Button variant="link" onClick={fetchDashboard}>Retry</Button>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">Labelforge operations overview for Nakoda Art & Craft.</p>
        </div>
        <div className="flex items-center">
          {lastUpdated && (
            <span className="text-xs text-muted-foreground mr-2">
              Last updated: {lastUpdated.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <Button variant="ghost" size="sm" onClick={fetchDashboard}>
            <RefreshCw className={`w-4 h-4 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {data.kpis.map(kpi => {
          const config = KPI_CONFIG[kpi.key] || { icon: <Layers className="w-4 h-4" />, format: (v: number) => String(v) };
          const navigable = kpi.key === 'active_orders' || kpi.key === 'hitl_open';
          return (
            <Card
              key={kpi.key}
              className={navigable ? 'cursor-pointer hover:border-primary/50 transition-colors' : ''}
              onClick={navigable ? () => setLocation(kpi.key === 'active_orders' ? '/orders' : '/hitl') : undefined}
            >
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{kpi.label}</CardTitle>
                {config.icon}
              </CardHeader>
              <CardContent>
                <div className={`text-3xl font-bold ${config.color || ''}`}>
                  {config.format(kpi.value)}
                </div>
                <p className="text-xs text-muted-foreground">{kpi.detail}</p>
                {kpi.trend !== null && kpi.trend !== undefined && (
                  <span className={`text-xs font-medium ${kpi.trend > 0 ? 'text-green-600' : kpi.trend < 0 ? 'text-red-600' : 'text-muted-foreground'}`}>
                    {kpi.trend > 0 ? '↑' : kpi.trend < 0 ? '↓' : '–'} {Math.abs(kpi.trend).toFixed(1)}
                  </span>
                )}
                {kpi.key === 'automation_rate' && data.automation_series.length > 0 && (
                  <div className="h-[40px] mt-2">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={data.automation_series}>
                        <Line type="monotone" dataKey="rate" stroke="var(--color-primary)" strokeWidth={2} dot={false} />
                        <YAxis domain={['dataMin - 10', 'dataMax + 10']} hide />
                        <Tooltip contentStyle={{ fontSize: '12px' }} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Automation Rate Chart */}
      {data.automation_series.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Automation Rate — 30 Day Trend</CardTitle>
              <span className="text-xs text-muted-foreground">Target: 60–85%</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="h-[200px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data.automation_series}>
                  <defs>
                    <linearGradient id="targetZone" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="var(--color-primary)" stopOpacity={0.1} />
                      <stop offset="100%" stopColor="var(--color-primary)" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickFormatter={(v) => `${v}%`} />
                  <Tooltip contentStyle={{ fontSize: '12px' }} formatter={(value: number) => [`${value}%`, 'Automation Rate']} labelFormatter={(label) => new Date(label).toLocaleDateString('en-US', { month: 'long', day: 'numeric' })} />
                  <ReferenceArea y1={60} y2={85} fill="#22c55e" fillOpacity={0.08} stroke="#22c55e" strokeOpacity={0.2} strokeDasharray="3 3" />
                  <Line type="monotone" dataKey="rate" stroke="var(--color-primary)" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Active Pipeline */}
        <Card className="col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Active Pipeline</CardTitle>
              <span className="text-xs text-primary cursor-pointer hover:underline" onClick={() => setLocation('/orders')}>View all</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="border rounded-md divide-y">
              {data.active_orders.length === 0 && (
                <div className="p-4 text-center text-sm text-muted-foreground">No active orders.</div>
              )}
              {data.active_orders.map(order => (
                <div
                  key={order.id}
                  className="p-3 flex items-center justify-between cursor-pointer hover:bg-muted/30 transition-colors"
                  onClick={() => setLocation(`/orders/${order.id}`)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-2 h-2 rounded-full shrink-0 ${STATE_DOTS[order.state] || 'bg-gray-400'}`} />
                    <div className="min-w-0">
                      <div className="font-mono text-sm font-medium text-primary">{order.po_number}</div>
                      <div className="text-xs text-muted-foreground truncate">
                        {order.importer_id} · {order.item_count} items
                        {order.issues > 0 && <span className="text-orange-600 ml-1"> · {order.issues} issues</span>}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <Badge variant="outline" className="text-[10px]">{order.state.replace(/_/g, ' ')}</Badge>
                    <div className="flex items-center gap-1.5 w-24">
                      <div className="h-1.5 flex-1 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-primary rounded-full" style={{ width: `${order.progress}%` }} />
                      </div>
                      <span className="text-xs text-muted-foreground tabular-nums w-7 text-right">{order.progress}%</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Recent Activity */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Recent Activity</CardTitle>
              <span className="text-xs text-primary cursor-pointer hover:underline" onClick={() => setLocation('/audit')}>View all</span>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {data.recent_activity.length === 0 && (
                <p className="text-sm text-muted-foreground text-center py-4">No recent activity.</p>
              )}
              {data.recent_activity.slice(0, 6).map(entry => (
                <div key={entry.id} className="flex gap-2.5">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0 mt-0.5
                    ${entry.actor_type === 'agent' ? 'bg-primary/10 text-primary' : 'bg-orange-100 text-orange-600'}`}>
                    {entry.actor_type === 'agent' ? <Bot className="w-3 h-3" /> : <User className="w-3 h-3" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs leading-snug truncate">
                      <span className="font-medium">{entry.actor}</span>{' '}
                      <span className="text-muted-foreground">{entry.detail}</span>
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5 flex items-center gap-1">
                      <Clock className="w-2.5 h-2.5" />
                      {new Date(entry.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
