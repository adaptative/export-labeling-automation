import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { AlertCircle, TrendingUp, TrendingDown, Edit2, ShieldAlert } from 'lucide-react';
import { useCurrentSpend, useBudgetEvents, useUpdateBudgetCap, type SpendingTier } from '@/hooks/useBudgets';
import { useAuthStore } from '@/store/authStore';

function tierColor(pct: number) {
  if (pct >= 80) return 'text-red-600';
  if (pct >= 50) return 'text-yellow-600';
  return 'text-green-600';
}

function progressColor(pct: number) {
  if (pct >= 80) return '[&>div]:bg-red-500';
  if (pct >= 50) return '[&>div]:bg-yellow-500';
  return '[&>div]:bg-green-500';
}

export default function Cost() {
  const role = useAuthStore((s) => s.role);
  const isAdmin = role === 'Admin';
  const { data: tiers, isLoading: tiersLoading } = useCurrentSpend();
  const [tierFilter, setTierFilter] = useState<string>('all');
  const { data: eventsData, isLoading: eventsLoading } = useBudgetEvents(
    tierFilter !== 'all' ? { tier: tierFilter } : undefined
  );

  const [editTier, setEditTier] = useState<SpendingTier | null>(null);
  const [newCap, setNewCap] = useState('');
  const [reason, setReason] = useState('');
  const updateCap = useUpdateBudgetCap();

  const anyBreakerActive = tiers?.some((t) => t.breaker_active);

  const handleSaveCap = () => {
    if (!editTier || !newCap || !reason) return;
    updateCap.mutate(
      { tenantId: 'tnt-nakoda-001', tier: editTier.id, new_cap: parseFloat(newCap), reason },
      { onSuccess: () => { setEditTier(null); setNewCap(''); setReason(''); } }
    );
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Cost & Budgets</h1>
          <p className="text-sm text-muted-foreground">Monitor spending across 4 tiers with breaker protection.</p>
        </div>
      </div>

      {anyBreakerActive && (
        <div className="flex items-center gap-2 bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-800 rounded-lg px-4 py-3">
          <ShieldAlert className="w-5 h-5 text-red-600 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-700 dark:text-red-400">Cost breaker ACTIVE</p>
            <p className="text-xs text-red-600/80 dark:text-red-400/70">
              {tiers?.filter((t) => t.breaker_active).map((t) => t.name).join(', ')} — operations paused
            </p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {tiersLoading
          ? Array.from({ length: 4 }).map((_, i) => (
              <Card key={i}><CardContent className="p-6"><div className="h-20 animate-pulse bg-muted rounded" /></CardContent></Card>
            ))
          : tiers?.map((tier) => {
              const pct = tier.cap > 0 ? (tier.current_spend / tier.cap) * 100 : 0;
              return (
                <Card key={tier.id} className={tier.breaker_active ? 'border-red-500 bg-red-50/50 dark:bg-red-950/20' : ''}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm font-medium">{tier.name}</CardTitle>
                      {isAdmin && (
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => { setEditTier(tier); setNewCap(String(tier.cap)); }}>
                          <Edit2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex items-baseline gap-1">
                      <span className={`text-2xl font-bold tabular-nums ${tierColor(pct)}`}>
                        {tier.current_spend.toLocaleString()}
                      </span>
                      <span className="text-sm text-muted-foreground">/ {tier.cap.toLocaleString()} {tier.unit}</span>
                    </div>
                    <Progress value={Math.min(pct, 100)} className={`h-2 ${progressColor(pct)}`} />
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">{pct.toFixed(1)}% used</span>
                      <span className={`flex items-center gap-0.5 ${tier.trend_pct >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                        {tier.trend_pct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {Math.abs(tier.trend_pct)}%
                      </span>
                    </div>
                    {tier.breaker_active && (
                      <Badge variant="destructive" className="text-[10px]">BREAKER ACTIVE</Badge>
                    )}
                  </CardContent>
                </Card>
              );
            })}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Breaker Event History</h2>
          <Select value={tierFilter} onValueChange={setTierFilter}>
            <SelectTrigger className="w-44 h-9">
              <SelectValue placeholder="All tiers" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All tiers</SelectItem>
              <SelectItem value="llm_inference">LLM Inference</SelectItem>
              <SelectItem value="api_calls">API Calls</SelectItem>
              <SelectItem value="storage">Storage</SelectItem>
              <SelectItem value="hitl">Human Review</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="border rounded-md bg-card shadow-sm">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead className="w-[180px]">Timestamp</TableHead>
                <TableHead className="w-[140px]">Tier</TableHead>
                <TableHead className="w-[100px]">Type</TableHead>
                <TableHead className="w-[160px]">Triggered By</TableHead>
                <TableHead>Action</TableHead>
                <TableHead className="w-[90px]">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {eventsLoading ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Loading...</TableCell></TableRow>
              ) : eventsData?.events.length === 0 ? (
                <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">No breaker events found.</TableCell></TableRow>
              ) : (
                eventsData?.events.map((evt) => (
                  <TableRow key={evt.id}>
                    <TableCell className="tabular-nums text-xs text-muted-foreground">
                      {new Date(evt.timestamp).toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </TableCell>
                    <TableCell className="text-sm">{evt.tier.replace('_', ' ')}</TableCell>
                    <TableCell>
                      <Badge variant={evt.event_type === 'breach' ? 'destructive' : 'outline'} className="text-[10px]">
                        {evt.event_type.toUpperCase()}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{evt.triggered_by}</TableCell>
                    <TableCell className="text-xs">{evt.action}</TableCell>
                    <TableCell>
                      <Badge variant={evt.status === 'active' ? 'destructive' : 'secondary'} className="text-[10px]">
                        {evt.status}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={!!editTier} onOpenChange={(open) => { if (!open) setEditTier(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Cap — {editTier?.name}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div>
              <Label>Current Cap</Label>
              <p className="text-sm text-muted-foreground">{editTier?.cap.toLocaleString()} {editTier?.unit}</p>
            </div>
            <div>
              <Label htmlFor="new-cap">New Cap</Label>
              <Input id="new-cap" type="number" value={newCap} onChange={(e) => setNewCap(e.target.value)} min={1} />
            </div>
            <div>
              <Label htmlFor="reason">Reason</Label>
              <Textarea id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this cap being changed?" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditTier(null)}>Cancel</Button>
            <Button onClick={handleSaveCap} disabled={!newCap || !reason || updateCap.isPending}>
              {updateCap.isPending ? 'Saving...' : 'Save'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
