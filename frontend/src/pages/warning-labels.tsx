import React, { useState, useMemo } from 'react';
import { useLocation } from 'wouter';
import { warningLabels } from '../lib/mocks/warningLabels';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Plus, Search, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';

const STATUS_META: Record<string, { color: string; icon: React.ReactNode }> = {
  approved: { color: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: <CheckCircle2 className="w-3 h-3" /> },
  pending:  { color: 'bg-yellow-50 text-yellow-700 border-yellow-200',   icon: <Clock className="w-3 h-3" /> },
  rejected: { color: 'bg-red-50 text-red-700 border-red-200',            icon: <AlertTriangle className="w-3 h-3" /> },
};

export default function WarningLabels() {
  const [, setLocation] = useLocation();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');

  const filtered = useMemo(() => {
    return warningLabels.filter(wl => {
      if (search && !wl.name.toLowerCase().includes(search.toLowerCase())) return false;
      if (statusFilter !== 'all' && wl.status !== statusFilter) return false;
      return true;
    });
  }, [search, statusFilter]);

  const stats = useMemo(() => ({
    approved: warningLabels.filter(w => w.status === 'approved').length,
    pending: warningLabels.filter(w => w.status === 'pending').length,
    total: warningLabels.length,
  }), []);

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Warning Labels</h1>
          <p className="text-sm text-muted-foreground">
            {stats.total} labels · {stats.approved} approved · {stats.pending} pending review
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">Propose Update</Button>
          <Button><Plus className="w-4 h-4 mr-1.5" /> Upload New Label</Button>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search labels..." className="pl-8 h-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-40 h-9">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filtered.map(wl => {
          const meta = STATUS_META[wl.status] || STATUS_META.approved;
          return (
            <Card key={wl.id} className="cursor-pointer hover:border-primary/50 transition-colors group">
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                  <div className="w-14 h-14 bg-muted border rounded-md mb-2 flex items-center justify-center text-xs text-muted-foreground font-mono shrink-0">
                    ⚠️
                  </div>
                  <Badge variant="outline" className={`text-[10px] gap-1 ${meta.color}`}>
                    {meta.icon}
                    {wl.status}
                  </Badge>
                </div>
                <CardTitle className="text-base leading-tight">{wl.name}</CardTitle>
                <div className="text-[11px] text-muted-foreground font-mono mt-0.5">{wl.id} · {wl.importerName}</div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-muted-foreground line-clamp-3 leading-relaxed italic" title={wl.wording}>
                  "{wl.wording}"
                </p>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-muted-foreground">Size: </span>
                    <span className="font-medium tabular-nums">{wl.size}</span>
                  </div>
                  <div>
                    <span className="text-muted-foreground">Placement: </span>
                    <span className="font-medium">{wl.placement}</span>
                  </div>
                </div>
                <div className="pt-2 border-t">
                  <div className="text-[10px] text-muted-foreground mb-1">Trigger:</div>
                  <code className="text-[10px] bg-muted px-1.5 py-0.5 rounded font-mono">{wl.triggerSummary}</code>
                </div>
                {wl.variants.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {wl.variants.map(v => (
                      <Badge key={v} variant="outline" className="text-[10px] px-1.5 py-0">{v}</Badge>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
        {filtered.length === 0 && (
          <div className="col-span-full text-center py-12 text-muted-foreground border rounded-md border-dashed">
            No warning labels match the current filters.
          </div>
        )}
      </div>
    </div>
  );
}
