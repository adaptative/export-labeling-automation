import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useRoute, useLocation } from 'wouter';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  ArrowLeft, Download, CheckCircle2, AlertCircle, Copy, Loader2,
  FileImage, FileText, Box, History,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { apiGet } from '../api/authInterceptor';
import {
  ArtifactResult, ItemHistoryResponse, OrderItemSummary,
  getApprovalPdf, getBundle, getDiecutSvg, getItem, getItemHistory,
  getLineDrawing,
} from '../api/itemArtifacts';

/* ── Types ─────────────────────────────────────────────────────────────── */

interface OrderDetail {
  id: string;
  importer_id: string;
  po_number: string;
  state: string;
  item_count: number;
  created_at: string;
  updated_at: string;
  items?: Array<{
    id: string;
    item_no: string;
    state: string;
    data?: Record<string, any>;
  }>;
}

interface ImporterDetail {
  id: string;
  name: string;
  code?: string;
}

interface ItemLoadState {
  order: OrderDetail | null;
  item: (OrderItemSummary & { data?: Record<string, any> }) | null;
  importer: ImporterDetail | null;
}

const STATE_LABELS: Record<string, string> = {
  CREATED: 'Created',
  INTAKE_CLASSIFIED: 'Intake',
  PARSED: 'Parsed',
  FUSED: 'Fused',
  COMPLIANCE_EVAL: 'Compliance Check',
  DRAWING_GENERATED: 'Drawings Ready',
  COMPOSED: 'Composed',
  VALIDATED: 'Validated',
  REVIEWED: 'Reviewed',
  DELIVERED: 'Delivered',
  HUMAN_BLOCKED: 'Human Review',
  FAILED: 'Failed',
};

function friendlyState(state: string): string {
  return STATE_LABELS[state] || state;
}

function stateBadge(state: string): React.ReactNode {
  if (state === 'DELIVERED' || state === 'VALIDATED' || state === 'REVIEWED') {
    return (
      <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-xs gap-1">
        <CheckCircle2 className="w-3 h-3" /> {friendlyState(state)}
      </Badge>
    );
  }
  if (state === 'FAILED' || state === 'HUMAN_BLOCKED') {
    return (
      <Badge variant="outline" className="bg-red-50 text-red-700 border-red-200 text-xs gap-1">
        <AlertCircle className="w-3 h-3" /> {friendlyState(state)}
      </Badge>
    );
  }
  return <Badge variant="outline" className="text-xs">{friendlyState(state)}</Badge>;
}

function DataRow({
  label, value, mono,
}: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between py-2 border-b border-dashed last:border-0 gap-3">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={`text-sm font-medium text-right ${mono ? 'font-mono tabular-nums' : ''}`}>
        {value ?? <span className="text-muted-foreground">—</span>}
      </span>
    </div>
  );
}

function MissingState({ reason, label }: { reason: string; label: string }) {
  const copy =
    reason === 'not_generated'
      ? `The ${label} has not been generated yet. Trigger the workflow agent or re-run compose for this item.`
      : reason === 'blob_missing'
        ? `The ${label} record exists but the underlying file is missing from storage.`
        : `The ${label} is unavailable.`;
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-16 px-6">
      <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-3">
        <AlertCircle className="w-6 h-6 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium">{label} unavailable</p>
      <p className="text-xs text-muted-foreground mt-1 max-w-sm">{copy}</p>
    </div>
  );
}

function ArtifactLoading() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-16">
      <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
      <p className="text-xs text-muted-foreground mt-2">Loading…</p>
    </div>
  );
}

export default function ItemPreview() {
  const [, params] = useRoute('/orders/:orderId/items/:itemId');
  const [, setLocation] = useLocation();
  const { toast } = useToast();

  const orderId = params?.orderId || '';
  const itemId = params?.itemId || '';

  const [loaded, setLoaded] = useState<ItemLoadState>({ order: null, item: null, importer: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [diecut, setDiecut] = useState<ArtifactResult | null>(null);
  const [approval, setApproval] = useState<ArtifactResult | null>(null);
  const [lineDrawing, setLineDrawing] = useState<ArtifactResult | null>(null);
  const [history, setHistory] = useState<ItemHistoryResponse | null>(null);

  // Stash created object URLs so we can revoke them on unmount / refetch.
  const blobUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    if (!orderId || !itemId) return;

    setLoading(true);
    setError(null);

    (async () => {
      try {
        const [order, item] = await Promise.all([
          apiGet<OrderDetail>(`/orders/${encodeURIComponent(orderId)}`),
          getItem(itemId),
        ]);

        // Try to load the importer, but don't fail the whole page if it 404s.
        let importer: ImporterDetail | null = null;
        if (order.importer_id) {
          try {
            importer = await apiGet<ImporterDetail>(
              `/importers/${encodeURIComponent(order.importer_id)}`,
            );
          } catch {
            importer = null;
          }
        }

        // Back-fill per-item data (description, UPC, etc.) from the order's
        // embedded items list — /items/{id} doesn't return `data`.
        const embedded = order.items?.find(i => i.id === itemId);
        const enrichedItem = embedded
          ? { ...item, data: embedded.data }
          : item;

        if (!cancelled) {
          setLoaded({ order, item: enrichedItem, importer });
        }
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load item');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [orderId, itemId]);

  // Fetch artifacts once the item is resolved.
  useEffect(() => {
    if (!loaded.item) return;
    let cancelled = false;

    // Revoke any previously-allocated object URLs.
    blobUrlsRef.current.forEach(u => URL.revokeObjectURL(u));
    blobUrlsRef.current = [];

    const track = (r: ArtifactResult) => {
      if (r.kind === 'blob') blobUrlsRef.current.push(r.url);
      return r;
    };

    Promise.all([
      getDiecutSvg(loaded.item.id).then(track).catch(() => null),
      getApprovalPdf(loaded.item.id).then(track).catch(() => null),
      getLineDrawing(loaded.item.id).then(track).catch(() => null),
      getItemHistory(loaded.item.id).catch(() => null),
    ]).then(([svg, pdf, line, hist]) => {
      if (cancelled) return;
      setDiecut(svg);
      setApproval(pdf);
      setLineDrawing(line);
      setHistory(hist);
    });

    return () => {
      cancelled = true;
    };
  }, [loaded.item?.id]);

  // Revoke on unmount.
  useEffect(() => {
    return () => {
      blobUrlsRef.current.forEach(u => URL.revokeObjectURL(u));
      blobUrlsRef.current = [];
    };
  }, []);

  const order = loaded.order;
  const item = loaded.item;
  const importer = loaded.importer;

  const itemData = (item?.data ?? {}) as Record<string, any>;

  /** Render any dimension field safely — handles strings, plain numbers,
   * or `{length, width, height, unit}` shaped objects. */
  const fmtDims = (v: any): string | null => {
    if (v == null) return null;
    if (typeof v === 'string') return v;
    if (typeof v === 'number') return String(v);
    if (typeof v === 'object') {
      const { length, width, height, depth, unit } = v as Record<string, any>;
      const parts = [length, width, height ?? depth].filter(p => p !== undefined && p !== null);
      if (parts.length === 0) return null;
      const u = typeof unit === 'string' ? ` ${unit}` : '';
      return `${parts.join(' × ')}${u}`;
    }
    return String(v);
  };

  const fmtScalar = (v: any): string | null => {
    if (v == null) return null;
    if (typeof v === 'string' || typeof v === 'number') return String(v);
    return null;
  };

  const itemName = fmtScalar(itemData.description) || item?.item_no || 'Item';
  const sku = fmtScalar(itemData.sku) || item?.item_no;
  const upc = fmtScalar(itemData.upc) ?? fmtScalar(itemData.gtin);
  const caseQty = fmtScalar(itemData.case_qty);
  const totalQty = typeof itemData.total_qty === 'number' ? itemData.total_qty : undefined;
  const material = fmtScalar(itemData.material);
  const finish = fmtScalar(itemData.finish);
  const productDims = fmtDims(itemData.product_dims);
  // Carton dims may be a single object or L/W/H triplet of numbers.
  const cartonDims =
    fmtDims(itemData.carton_dims) ??
    (itemData.box_L && itemData.box_W && itemData.box_H
      ? `${itemData.box_L} × ${itemData.box_W} × ${itemData.box_H}${itemData.box_unit ? ' ' + itemData.box_unit : ''}`
      : null);
  const totalCartons = typeof itemData.total_cartons === 'number' ? itemData.total_cartons : undefined;

  const copyItemData = () => {
    if (!item) return;
    navigator.clipboard?.writeText(JSON.stringify({
      id: item.id, order_id: item.order_id, item_no: item.item_no,
      state: item.state, data: item.data ?? {},
    }, null, 2));
    toast({ title: 'Copied', description: 'Item JSON copied to clipboard.' });
  };

  const downloadBundle = async () => {
    if (!item) return;
    try {
      const bundle = await getBundle(item.id);
      if (bundle.kind === 'missing') {
        toast({
          title: 'Bundle not ready',
          description: bundle.detail ||
            (bundle.reason === 'blob_missing'
              ? 'Bundle row exists but the ZIP file is missing from storage.'
              : 'The printer bundle has not been generated yet.'),
        });
        return;
      }
      const a = document.createElement('a');
      a.href = bundle.url;
      a.download = `${order?.po_number || 'order'}_${item.item_no}_bundle.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      toast({ title: 'Bundle downloading', description: 'Your printer ZIP is on its way.' });
      // Leak-free: the object URL is tracked and revoked on unmount/refetch.
      blobUrlsRef.current.push(bundle.url);
    } catch (e) {
      toast({
        title: 'Download failed',
        description: e instanceof Error ? e.message : 'Unknown error',
        variant: 'destructive' as any,
      });
    }
  };

  if (loading) {
    return (
      <div className="p-12 flex flex-col items-center text-muted-foreground">
        <Loader2 className="w-6 h-6 animate-spin" />
        <p className="text-sm mt-3">Loading item…</p>
      </div>
    );
  }

  if (error || !order || !item) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">{error || 'Item not found'}</p>
        <Button variant="link" onClick={() => setLocation(orderId ? `/orders/${orderId}` : '/orders')}>
          Back {orderId ? 'to Order' : 'to Orders'}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      <div className="px-6 py-4 border-b shrink-0 bg-card z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="h-8 w-8"
                    onClick={() => setLocation(`/orders/${orderId}`)}>
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-bold">{itemName}</h1>
                {stateBadge(item.state)}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                <span className="font-mono">{item.item_no}</span>
                {order.po_number ? <> · {order.po_number}</> : null}
                {importer?.name ? <> · {importer.name}</> : null}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={copyItemData}>
              <Copy className="w-3.5 h-3.5 mr-1.5" /> Copy Data
            </Button>
            <Button variant="outline" size="sm" onClick={downloadBundle}>
              <Download className="w-3.5 h-3.5 mr-1.5" /> Download Bundle
            </Button>
          </div>
        </div>
      </div>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-auto">
          <Tabs defaultValue="diecut" className="h-full flex flex-col">
            <div className="px-6 pt-3 border-b bg-background shrink-0">
              <TabsList>
                <TabsTrigger value="diecut" className="gap-1.5"><Box className="w-3.5 h-3.5" /> Die-cut SVG</TabsTrigger>
                <TabsTrigger value="approval" className="gap-1.5"><FileText className="w-3.5 h-3.5" /> Approval PDF</TabsTrigger>
                <TabsTrigger value="lineart" className="gap-1.5"><FileImage className="w-3.5 h-3.5" /> Line Drawing</TabsTrigger>
                <TabsTrigger value="history" className="gap-1.5"><History className="w-3.5 h-3.5" /> History</TabsTrigger>
              </TabsList>
            </div>

            <div className="flex-1 overflow-auto bg-muted/20">
              {/* Die-cut SVG */}
              <TabsContent value="diecut" className="m-0 p-6 h-full">
                <div className="w-full max-w-3xl mx-auto h-full">
                  <div className="aspect-[4/3] bg-white border-2 rounded-lg shadow-sm overflow-hidden relative">
                    {diecut === null ? (
                      <ArtifactLoading />
                    ) : diecut.kind === 'blob' ? (
                      <iframe
                        title="Die-cut SVG"
                        src={diecut.url}
                        className="w-full h-full border-0"
                      />
                    ) : (
                      <MissingState reason={diecut.reason} label="die-cut SVG" />
                    )}
                  </div>
                  {/*
                    The content hash is useful for engineers triaging a
                    misrender but confusing to the reviewers/buyers that
                    live inside this pane — it's now surfaced only in the
                    Artifacts tab and via the copy-link action.
                  */}
                </div>
              </TabsContent>

              {/* Approval PDF */}
              <TabsContent value="approval" className="m-0 p-6 h-full">
                <div className="w-full max-w-3xl mx-auto h-full">
                  <div className="aspect-[1/1.414] bg-white border-2 rounded-lg shadow-sm overflow-hidden">
                    {approval === null ? (
                      <ArtifactLoading />
                    ) : approval.kind === 'blob' ? (
                      <iframe
                        title="Approval PDF"
                        src={approval.url}
                        className="w-full h-full border-0"
                      />
                    ) : (
                      <MissingState reason={approval.reason} label="approval PDF" />
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* Line drawing */}
              <TabsContent value="lineart" className="m-0 p-6 h-full">
                <div className="w-full max-w-2xl mx-auto h-full">
                  <div className="aspect-square bg-white border-2 rounded-lg shadow-sm overflow-hidden">
                    {lineDrawing === null ? (
                      <ArtifactLoading />
                    ) : lineDrawing.kind === 'blob' ? (
                      <iframe
                        title="Line drawing"
                        src={lineDrawing.url}
                        className="w-full h-full border-0"
                      />
                    ) : (
                      <MissingState reason={lineDrawing.reason} label="line drawing" />
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* History */}
              <TabsContent value="history" className="m-0 p-6">
                <div className="max-w-2xl mx-auto space-y-3">
                  {history === null ? (
                    <ArtifactLoading />
                  ) : history.events.length === 0 ? (
                    <p className="text-sm text-muted-foreground text-center py-8">
                      No history recorded yet.
                    </p>
                  ) : (
                    history.events.map((e) => (
                      <div key={e.step} className="flex gap-3 py-2 border-b border-dashed last:border-0">
                        <div className="w-6 h-6 rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0 text-[10px]">
                          {e.actor_type === 'human' ? '👤' :
                           e.actor_type === 'agent' ? '🤖' : '⚡'}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm">
                            {e.detail || e.action}
                            {e.from_state && e.to_state && (
                              <span className="text-xs text-muted-foreground ml-2">
                                {e.from_state} → <span className="font-medium">{e.to_state}</span>
                              </span>
                            )}
                          </p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            {e.actor || e.actor_type} · {new Date(e.at).toLocaleString()}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </TabsContent>
            </div>
          </Tabs>
        </div>

        {/* Sidebar */}
        <div className="w-72 border-l bg-card shrink-0 overflow-y-auto hidden lg:block">
          <div className="p-4 border-b">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Item Data
            </h3>
          </div>
          <div className="px-4 py-2">
            <DataRow label="Item #" value={item.item_no} mono />
            <DataRow label="State" value={friendlyState(item.state)} />
            {sku ? <DataRow label="SKU" value={sku} mono /> : null}
            {upc ? <DataRow label="UPC" value={upc} mono /> : null}
            {material ? <DataRow label="Material" value={material} /> : null}
            {finish ? <DataRow label="Finish" value={finish} /> : null}
            {productDims ? <DataRow label="Product Size" value={productDims} mono /> : null}
            {cartonDims ? <DataRow label="Carton Size" value={cartonDims} mono /> : null}
            {caseQty !== null && <DataRow label="Case Qty" value={caseQty} mono />}
            {totalQty !== undefined && (
              <DataRow label="Total Qty" value={Number(totalQty).toLocaleString()} mono />
            )}
            {totalCartons !== undefined && (
              <DataRow label="Total Cartons" value={Number(totalCartons).toLocaleString()} mono />
            )}
            <DataRow
              label="Order"
              value={
                <button
                  className="text-primary hover:underline"
                  onClick={() => setLocation(`/orders/${order.id}`)}
                >
                  {order.po_number || order.id}
                </button>
              }
            />
            {importer?.name && <DataRow label="Importer" value={importer.name} />}
            {item.rules_snapshot_id && (
              <DataRow label="Rules Snapshot" value={item.rules_snapshot_id} mono />
            )}
            <DataRow
              label="State Changed"
              value={item.state_changed_at
                ? new Date(item.state_changed_at).toLocaleString()
                : '—'}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
