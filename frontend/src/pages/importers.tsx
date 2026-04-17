import React, { useState, useEffect, useCallback } from 'react';
import { useLocation } from 'wouter';
import { apiGet } from '../api/authInterceptor';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { Plus, AlertCircle, CheckCircle2, Clock, PauseCircle, Search, RefreshCw } from 'lucide-react';

/* ── Types matching backend response ─────────────────────────────────── */

interface ImporterSummary {
  id: string;
  name: string;
  code: string;
  status: string;
  countries: string[];
  profile_version: number;
  onboarding_progress: number;
  orders_mtd: number;
  open_hitl: number;
  required_fields: string[];
}

interface ImporterListResponse {
  importers: ImporterSummary[];
  total: number;
}

/* ── Status config ───────────────────────────────────────────────────── */

const STATUS_COLORS: Record<string, string> = {
  active: 'bg-green-100 text-green-700 border-green-200',
  onboarding: 'bg-blue-100 text-blue-700 border-blue-200',
  invited: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  inactive: 'bg-gray-100 text-gray-600 border-gray-200',
  paused: 'bg-gray-100 text-gray-600 border-gray-200',
};

const STATUS_ICONS: Record<string, React.FC<{ className?: string }>> = {
  active: CheckCircle2,
  onboarding: Clock,
  invited: AlertCircle,
  inactive: PauseCircle,
  paused: PauseCircle,
};

/* ── Skeleton loader ─────────────────────────────────────────────────── */

function ImporterCardSkeleton() {
  return (
    <Card className="min-h-[200px]">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-5 w-16" />
        </div>
        <Skeleton className="h-3 w-20 mt-1" />
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <Skeleton className="h-1.5 w-full mt-4" />
        </div>
        <div className="grid grid-cols-3 gap-2 text-center">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Main component ──────────────────────────────────────────────────── */

export default function Importers() {
  const [, setLocation] = useLocation();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [importers, setImporters] = useState<ImporterSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Debounced search — waits 300ms after the user stops typing */
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  const fetchImporters = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (debouncedSearch) params.set('search', debouncedSearch);
      const qs = params.toString();
      // Adapter: the backend's ImporterProfile (contracts/models.py) returns
      // `importer_id`, not `id`, and omits the UI-only summary fields. Map
      // them here so card clicks produce `/importers/<real-id>` instead of
      // `/importers/undefined`.
      const data = await apiGet<{ importers: Array<Record<string, unknown>>; total: number }>(
        `/importers${qs ? `?${qs}` : ''}`,
      );
      const summaries: ImporterSummary[] = data.importers.map((raw) => ({
        id: (raw.id as string) ?? (raw.importer_id as string) ?? '',
        name: (raw.name as string) ?? '',
        code: (raw.code as string) ?? '',
        status: (raw.status as string) ?? 'active',
        countries: (raw.countries as string[]) ?? [],
        profile_version: (raw.version as number) ?? (raw.profile_version as number) ?? 0,
        onboarding_progress: (raw.onboarding_progress as number) ?? 100,
        orders_mtd: (raw.orders_mtd as number) ?? 0,
        open_hitl: (raw.open_hitl as number) ?? 0,
        required_fields: (raw.required_fields as string[]) ?? [],
      }));
      setImporters(summaries);
      setTotal(data.total);
    } catch (e: any) {
      setError(e.message || 'Failed to load importers');
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch]);

  useEffect(() => { fetchImporters(); }, [fetchImporters]);

  const stats = {
    total,
    active: importers.filter((i) => i.status === 'active').length,
    onboarding: importers.filter((i) => i.status === 'onboarding').length,
    openHitl: importers.reduce((sum, i) => sum + (i.open_hitl ?? 0), 0),
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Importers</h1>
          <p className="text-sm text-muted-foreground">Manage client requirements and label protocols.</p>
        </div>
        <Button onClick={() => setLocation('/onboarding/importer')}>
          <Plus className="w-4 h-4 mr-2" /> Add Importer
        </Button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search importers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Button variant="outline" size="icon" onClick={fetchImporters} disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4">
        <div className="border rounded-lg p-4 bg-card">
          <p className="text-xs text-muted-foreground">Total Importers</p>
          <p className="text-2xl font-bold font-mono tabular-nums mt-1">{loading ? '-' : stats.total}</p>
        </div>
        <div className="border rounded-lg p-4 bg-card">
          <p className="text-xs text-muted-foreground">Active</p>
          <p className="text-2xl font-bold font-mono tabular-nums text-green-600 mt-1">{loading ? '-' : stats.active}</p>
        </div>
        <div className="border rounded-lg p-4 bg-card">
          <p className="text-xs text-muted-foreground">Onboarding</p>
          <p className="text-2xl font-bold font-mono tabular-nums text-blue-600 mt-1">{loading ? '-' : stats.onboarding}</p>
        </div>
        <div className="border rounded-lg p-4 bg-card">
          <p className="text-xs text-muted-foreground">Open HiTL</p>
          <p className={`text-2xl font-bold font-mono tabular-nums mt-1 ${stats.openHitl > 0 ? 'text-orange-600' : ''}`}>
            {loading ? '-' : stats.openHitl}
          </p>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive border border-destructive/30 bg-destructive/5 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 shrink-0" />
          {error}
          <Button variant="link" size="sm" className="ml-auto" onClick={fetchImporters}>Retry</Button>
        </div>
      )}

      {/* Importer cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {loading ? (
          <>
            {Array.from({ length: 8 }).map((_, i) => (
              <ImporterCardSkeleton key={i} />
            ))}
          </>
        ) : (
          <>
            {importers.map((imp) => {
              const StatusIcon = STATUS_ICONS[imp.status] || AlertCircle;
              return (
                <Card
                  key={imp.id}
                  className="cursor-pointer hover:border-primary transition-colors"
                  onClick={() => setLocation(`/importers/${imp.id}`)}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <CardTitle className="text-base leading-snug">{imp.name}</CardTitle>
                        {imp.code && (
                          <span className="text-xs font-mono text-muted-foreground">{imp.code}</span>
                        )}
                      </div>
                      <Badge variant="outline" className={`text-xs shrink-0 ${STATUS_COLORS[imp.status] ?? ''}`}>
                        <StatusIcon className="w-3 h-3 mr-1" />
                        {imp.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">{imp.countries?.join(', ')}</p>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div>
                      <div className="flex justify-between text-xs mb-1.5">
                        <span className="text-muted-foreground">Onboarding</span>
                        <span className="font-mono font-medium">{imp.onboarding_progress ?? 0}%</span>
                      </div>
                      <Progress value={imp.onboarding_progress ?? 0} className="h-1.5" />
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div>
                        <div className="text-xs text-muted-foreground">Orders MTD</div>
                        <div className="font-mono font-semibold text-sm">{imp.orders_mtd ?? 0}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Open HiTL</div>
                        <div className={`font-mono font-semibold text-sm ${(imp.open_hitl ?? 0) > 0 ? 'text-orange-600' : ''}`}>
                          {imp.open_hitl ?? 0}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Version</div>
                        <div className="font-mono font-semibold text-sm">v{imp.profile_version ?? 1}</div>
                      </div>
                    </div>
                    {imp.status === 'invited' && (
                      <div className="flex items-center gap-1.5 text-xs text-yellow-700 bg-yellow-50 rounded px-2 py-1.5 border border-yellow-200">
                        <AlertCircle className="w-3 h-3 shrink-0" />
                        Awaiting PDF approval
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}

            {/* Add new card */}
            <Card
              className="cursor-pointer hover:border-primary transition-colors border-dashed flex items-center justify-center min-h-[200px]"
              onClick={() => setLocation('/onboarding/importer')}
            >
              <div className="text-center text-muted-foreground p-6">
                <Plus className="w-8 h-8 mx-auto mb-2 opacity-40" />
                <p className="text-sm font-medium">Add Importer</p>
                <p className="text-xs mt-1 opacity-70">Run the onboarding wizard</p>
              </div>
            </Card>
          </>
        )}
      </div>

      {/* Empty state when not loading */}
      {!loading && !error && importers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <AlertCircle className="w-8 h-8 mb-3 opacity-40" />
          <p className="text-sm font-medium">No importers found</p>
          {debouncedSearch && (
            <p className="text-xs mt-1 opacity-70">Try a different search term</p>
          )}
        </div>
      )}
    </div>
  );
}
