/**
 * Compliance Rules — Sprint 11 / INT-010.
 *
 * Lives at /rules. Replaces the old mock-driven table with the live
 * `/api/v1/rules/*` surface (list, create, update, dry-run, promote,
 * rollback, audit-log). Click a row → side-sheet with overview +
 * dry-run + history. "Propose new rule" and "Edit staged rule" both
 * open the shared RuleFormModal.
 */
import React, { useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Plus, Search, CheckCircle2, Clock, AlertTriangle, RefreshCw,
} from 'lucide-react';

import { ComplianceRule, useRules } from '@/hooks/useRules';
import { RuleFormModal } from '@/components/RuleFormModal';
import { RuleDetailSheet } from '@/components/RuleDetailSheet';

const STATUS_META: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  active: { color: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: <CheckCircle2 className="w-3 h-3" />, label: 'active' },
  staged: { color: 'bg-yellow-50 text-yellow-700 border-yellow-200',    icon: <Clock className="w-3 h-3" />,        label: 'staged' },
};

const REGIONS = ['all', 'US', 'US-CA', 'EU', 'UK', 'CA', 'AU', 'JP'];
const PLACEMENTS = ['all', 'both', 'carton', 'product', 'hangtag'];

export default function Rules() {
  const [search, setSearch] = useState('');
  const [region, setRegion] = useState('all');
  const [placement, setPlacement] = useState('all');
  const [status, setStatus] = useState<'all' | 'active' | 'staged'>('all');

  const [formOpen, setFormOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<ComplianceRule | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const filters = useMemo(() => ({
    region: region === 'all' ? undefined : region,
    placement: placement === 'all' ? undefined : placement,
    active: status === 'all' ? undefined : status === 'active',
    limit: 200,
  }), [region, placement, status]);

  const rulesQuery = useRules(filters);

  const rules = rulesQuery.data?.rules ?? [];
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rules;
    return rules.filter(
      (r) =>
        r.code.toLowerCase().includes(q) ||
        r.title.toLowerCase().includes(q) ||
        (r.description ?? '').toLowerCase().includes(q),
    );
  }, [rules, search]);

  const stats = useMemo(() => ({
    total: rules.length,
    active: rules.filter((r) => r.active).length,
    staged: rules.filter((r) => !r.active).length,
  }), [rules]);

  const selectedRule = useMemo(
    () => (selectedId ? rules.find((r) => r.id === selectedId) ?? null : null),
    [selectedId, rules],
  );

  const handleRowClick = (rule: ComplianceRule) => {
    setSelectedId(rule.id);
    setDetailOpen(true);
  };

  const handleEditFromDetail = (rule: ComplianceRule) => {
    setEditingRule(rule);
    setDetailOpen(false);
    setFormOpen(true);
  };

  const handleNewRule = () => {
    setEditingRule(null);
    setFormOpen(true);
  };

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Compliance Rules</h1>
          <p className="text-sm text-muted-foreground">
            {rulesQuery.isLoading
              ? 'Loading…'
              : `${stats.active} active · ${stats.staged} staged · ${stats.total} total`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => rulesQuery.refetch()} disabled={rulesQuery.isFetching}>
            <RefreshCw className={`w-4 h-4 ${rulesQuery.isFetching ? 'animate-spin' : ''}`} />
          </Button>
          <Button onClick={handleNewRule}>
            <Plus className="w-4 h-4 mr-1.5" /> Propose new rule
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search code, title, description..."
            className="pl-8 h-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select value={status} onValueChange={(v) => setStatus(v as typeof status)}>
          <SelectTrigger className="w-36 h-9">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="staged">Staged</SelectItem>
          </SelectContent>
        </Select>
        <Select value={region} onValueChange={setRegion}>
          <SelectTrigger className="w-36 h-9">
            <SelectValue placeholder="Region" />
          </SelectTrigger>
          <SelectContent>
            {REGIONS.map((r) => (
              <SelectItem key={r} value={r}>{r === 'all' ? 'All regions' : r}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={placement} onValueChange={setPlacement}>
          <SelectTrigger className="w-40 h-9">
            <SelectValue placeholder="Placement" />
          </SelectTrigger>
          <SelectContent>
            {PLACEMENTS.map((p) => (
              <SelectItem key={p} value={p}>{p === 'all' ? 'All placements' : p}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Error */}
      {rulesQuery.isError && (
        <div className="flex items-center gap-2 text-sm text-destructive border border-destructive/30 bg-destructive/5 rounded-lg p-3">
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {(rulesQuery.error as Error)?.message ?? 'Failed to load rules'}
          <Button variant="link" size="sm" className="ml-auto" onClick={() => rulesQuery.refetch()}>Retry</Button>
        </div>
      )}

      {/* Table */}
      <div className="border rounded-md bg-card shadow-sm overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead className="w-[180px]">Code</TableHead>
              <TableHead>Title</TableHead>
              <TableHead className="w-[90px]">Region</TableHead>
              <TableHead className="w-[110px]">Placement</TableHead>
              <TableHead className="w-[80px]">Version</TableHead>
              <TableHead className="w-[100px] text-center">Status</TableHead>
              <TableHead className="w-[160px]">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rulesQuery.isLoading ? (
              Array.from({ length: 6 }).map((_, i) => <RuleRowSkeleton key={i} />)
            ) : filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                  {search || region !== 'all' || placement !== 'all' || status !== 'all'
                    ? 'No rules match the current filters.'
                    : 'No rules yet — propose one to get started.'}
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((rule) => {
                const meta = STATUS_META[rule.active ? 'active' : 'staged'];
                return (
                  <TableRow
                    key={rule.id}
                    className="cursor-pointer hover:bg-muted/30 transition-colors"
                    onClick={() => handleRowClick(rule)}
                  >
                    <TableCell className="font-mono text-xs font-medium">{rule.code}</TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{rule.title}</div>
                      {rule.description && (
                        <div className="text-xs text-muted-foreground line-clamp-1">{rule.description}</div>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">{rule.region}</TableCell>
                    <TableCell className="text-xs">{rule.placement}</TableCell>
                    <TableCell className="font-mono text-xs">v{rule.version}</TableCell>
                    <TableCell className="text-center">
                      <Badge variant="outline" className={`text-xs gap-1 ${meta.color}`}>
                        {meta.icon}
                        {meta.label}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground tabular-nums">
                      {new Date(rule.updated_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>

      <RuleFormModal
        open={formOpen}
        onOpenChange={(o) => {
          setFormOpen(o);
          if (!o) setEditingRule(null);
        }}
        rule={editingRule}
        onSaved={(saved) => {
          // If it's a new rule, select it so the user can immediately see it.
          setSelectedId(saved.id);
        }}
      />

      <RuleDetailSheet
        ruleId={selectedId}
        rule={selectedRule}
        open={detailOpen}
        onOpenChange={setDetailOpen}
        onEdit={handleEditFromDetail}
      />
    </div>
  );
}

function RuleRowSkeleton() {
  return (
    <TableRow>
      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
      <TableCell><Skeleton className="h-4 w-64" /></TableCell>
      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
      <TableCell><Skeleton className="h-4 w-10" /></TableCell>
      <TableCell><Skeleton className="h-5 w-16 mx-auto" /></TableCell>
      <TableCell><Skeleton className="h-4 w-20" /></TableCell>
    </TableRow>
  );
}
