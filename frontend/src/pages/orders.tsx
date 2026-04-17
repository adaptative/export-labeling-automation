import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { useLocation } from 'wouter';
import { apiGet } from '../api/authInterceptor';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Search, Plus, Download, AlertTriangle, CheckCircle2,
  Clock, Loader2, XCircle, Pause, RefreshCw, ChevronLeft, ChevronRight,
} from 'lucide-react';

/* ── Types matching backend response ─────────────────────────────────── */

interface OrderSummary {
  id: string;
  importer_id: string;
  po_number: string;
  state: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

interface OrderListResponse {
  orders: OrderSummary[];
  total: number;
}

/* ── State badge config ──────────────────────────────────────────────── */

const STATE_META: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  CREATED:          { color: 'bg-gray-100 text-gray-700 border-gray-200',       icon: <Clock className="w-3 h-3" />,          label: 'Created' },
  IN_PROGRESS:      { color: 'bg-sky-50 text-sky-700 border-sky-200',            icon: <Loader2 className="w-3 h-3 animate-spin" />, label: 'In Progress' },
  HUMAN_BLOCKED:    { color: 'bg-orange-50 text-orange-700 border-orange-200',   icon: <Pause className="w-3 h-3" />,           label: 'HiTL Blocked' },
  READY_TO_DELIVER: { color: 'bg-yellow-50 text-yellow-700 border-yellow-200',   icon: <AlertTriangle className="w-3 h-3" />,   label: 'Ready' },
  ATTENTION:        { color: 'bg-red-50 text-red-700 border-red-200',            icon: <XCircle className="w-3 h-3" />,         label: 'Attention' },
  DELIVERED:        { color: 'bg-emerald-50 text-emerald-700 border-emerald-200',icon: <CheckCircle2 className="w-3 h-3" />,    label: 'Delivered' },
};

const ALL_STATES = ['CREATED', 'IN_PROGRESS', 'HUMAN_BLOCKED', 'READY_TO_DELIVER', 'ATTENTION', 'DELIVERED'];

const PAGE_SIZE = 20;

const IMPORTERS = ['IMP-ACME', 'IMP-GLOBEX', 'IMP-INITECH'];

function readURLParams() {
  const params = new URLSearchParams(window.location.search);
  return {
    search: params.get('search') ?? '',
    stateFilter: params.get('state') ?? 'all',
    importerFilter: params.get('importer_id') ?? 'all',
    offset: Number(params.get('offset') ?? 0),
  };
}

export default function Orders() {
  const [, setLocation] = useLocation();

  const initial = useMemo(() => readURLParams(), []);

  const [search, setSearch] = useState(initial.search);
  const [stateFilter, setStateFilter] = useState<string>(initial.stateFilter);
  const [importerFilter, setImporterFilter] = useState<string>(initial.importerFilter);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(initial.offset);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Debounced search — waits 300ms after the user stops typing */
  const [debouncedSearch, setDebouncedSearch] = useState(search);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(timer);
  }, [search]);

  /* Persist filters in URL query string */
  useEffect(() => {
    const params = new URLSearchParams();
    if (debouncedSearch) params.set('search', debouncedSearch);
    if (stateFilter !== 'all') params.set('state', stateFilter);
    if (importerFilter !== 'all') params.set('importer_id', importerFilter);
    if (offset > 0) params.set('offset', String(offset));
    const qs = params.toString();
    window.history.replaceState(null, '', qs ? `?${qs}` : window.location.pathname);
  }, [debouncedSearch, stateFilter, importerFilter, offset]);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (stateFilter !== 'all') params.set('state', stateFilter);
      if (importerFilter !== 'all') params.set('importer_id', importerFilter);
      if (debouncedSearch) params.set('search', debouncedSearch);
      params.set('limit', String(PAGE_SIZE));
      params.set('offset', String(offset));
      const qs = params.toString();
      const data = await apiGet<OrderListResponse>(`/orders${qs ? `?${qs}` : ''}`);
      setOrders(data.orders);
      setTotal(data.total);
    } catch (e: any) {
      setError(e.message || 'Failed to load orders');
    } finally {
      setLoading(false);
    }
  }, [stateFilter, importerFilter, debouncedSearch, offset]);

  useEffect(() => { fetchOrders(); }, [fetchOrders]);

  // Reset offset when filters change
  useEffect(() => { setOffset(0); }, [stateFilter, importerFilter, debouncedSearch]);

  const stats = useMemo(() => {
    const active = orders.filter(o => !['DELIVERED'].includes(o.state)).length;
    const blocked = orders.filter(o => o.state === 'HUMAN_BLOCKED').length;
    return { active, blocked, total };
  }, [orders, total]);

  const totalPages = Math.ceil(total / PAGE_SIZE);
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const handleExportCSV = async () => {
    const params = new URLSearchParams();
    if (stateFilter !== 'all') params.set('state', stateFilter);
    if (importerFilter !== 'all') params.set('importer_id', importerFilter);
    if (debouncedSearch) params.set('search', debouncedSearch);
    const qs = params.toString();
    try {
      const response = await fetch(`/api/v1/orders/export${qs ? `?${qs}` : ''}`, { credentials: 'include' });
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `orders-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setError(e.message || 'CSV export failed');
    }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Orders</h1>
          <p className="text-sm text-muted-foreground">
            {stats.active} active · {stats.blocked} blocked · {total} total
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleExportCSV} disabled={orders.length === 0}>
            <Download className="w-4 h-4 mr-1.5" /> Export CSV
          </Button>
          <Button onClick={() => setLocation('/orders/new')} data-testid="btn-new-order">
            <Plus className="w-4 h-4 mr-1.5" /> New Order
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative w-64">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search PO number or ID..."
            className="pl-8 h-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="input-search-orders"
          />
        </div>
        <Select value={stateFilter} onValueChange={setStateFilter}>
          <SelectTrigger className="w-44 h-9">
            <SelectValue placeholder="All states" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All states</SelectItem>
            {ALL_STATES.map(s => (
              <SelectItem key={s} value={s}>{STATE_META[s]?.label || s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={importerFilter} onValueChange={setImporterFilter}>
          <SelectTrigger className="w-44 h-9">
            <SelectValue placeholder="All importers" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All importers</SelectItem>
            {IMPORTERS.map(imp => (
              <SelectItem key={imp} value={imp}>{imp}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="ghost" size="sm" onClick={fetchOrders} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </Button>
        {(stateFilter !== 'all' || importerFilter !== 'all' || search) && (
          <Button variant="ghost" size="sm" onClick={() => { setSearch(''); setStateFilter('all'); setImporterFilter('all'); }}>
            Clear filters
          </Button>
        )}
      </div>

      {error && (
        <div className="text-sm text-red-600 bg-red-50 p-3 rounded-md border border-red-200">
          {error}
        </div>
      )}

      <div className="border rounded-md bg-card shadow-sm">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead className="w-[160px]">Order ID</TableHead>
              <TableHead className="w-[130px]">PO Number</TableHead>
              <TableHead>Importer</TableHead>
              <TableHead className="text-center w-[70px]">Items</TableHead>
              <TableHead className="w-[140px]">State</TableHead>
              <TableHead className="w-[130px]">Created</TableHead>
              <TableHead className="w-[130px]">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && orders.length === 0 && Array.from({ length: 6 }).map((_, i) => (
              <TableRow key={`skel-${i}`}>
                <TableCell><div className="h-4 w-24 bg-muted rounded animate-pulse" /></TableCell>
                <TableCell><div className="h-4 w-20 bg-muted rounded animate-pulse" /></TableCell>
                <TableCell><div className="h-4 w-28 bg-muted rounded animate-pulse" /></TableCell>
                <TableCell className="text-center"><div className="h-4 w-6 bg-muted rounded animate-pulse mx-auto" /></TableCell>
                <TableCell><div className="h-5 w-20 bg-muted rounded-full animate-pulse" /></TableCell>
                <TableCell><div className="h-4 w-20 bg-muted rounded animate-pulse" /></TableCell>
                <TableCell><div className="h-4 w-20 bg-muted rounded animate-pulse" /></TableCell>
              </TableRow>
            ))}
            {!loading && orders.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground py-12">
                  No orders match the current filters.
                </TableCell>
              </TableRow>
            )}
            {orders.map((order) => {
              const meta = STATE_META[order.state] || STATE_META.CREATED;
              return (
                <TableRow
                  key={order.id}
                  className="cursor-pointer hover:bg-muted/30 transition-colors"
                  onClick={() => setLocation(`/orders/${order.id}`)}
                  data-testid={`row-order-${order.id}`}
                >
                  <TableCell className="font-mono text-xs text-muted-foreground">{order.id}</TableCell>
                  <TableCell className="font-mono font-semibold text-primary text-sm">{order.po_number}</TableCell>
                  <TableCell className="text-sm">{order.importer_id}</TableCell>
                  <TableCell className="text-center font-mono text-sm tabular-nums">{order.item_count}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={`${meta.color} text-xs gap-1 whitespace-nowrap`}>
                      {meta.icon}
                      {meta.label}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground tabular-nums">
                    {new Date(order.created_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground tabular-nums">
                    {new Date(order.updated_at).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}</span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline" size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              <ChevronLeft className="w-4 h-4" />
            </Button>
            <span>Page {currentPage} of {totalPages}</span>
            <Button
              variant="outline" size="sm"
              disabled={offset + PAGE_SIZE >= total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
