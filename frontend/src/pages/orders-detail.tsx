import React, { useState, useEffect, useCallback } from 'react';
import { useRoute, useLocation } from 'wouter';
import { apiGet, apiPost } from '../api/authInterceptor';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import {
  CheckCircle2, CircleDashed, Loader2, AlertCircle, XCircle, Slash,
  ArrowLeft, Download, Send, Printer, Eye, FileText, FileSpreadsheet,
  MessageSquare, Clock, ChevronRight, AlertTriangle, Pause, RefreshCw,
  Bot, User, CheckCheck,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAgentTypingByThread } from '@/hooks/useHitl';

/* ── Types matching backend responses ─────────────────────────────────── */

interface OrderSummary {
  id: string;
  importer_id: string;
  po_number: string;
  state: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

interface OrderItem {
  id: string;
  order_id: string;
  item_no: string;
  state: string;
  state_changed_at?: string;
  rules_snapshot_id?: string;
  data?: {
    description?: string;
    upc?: string;
    case_qty?: string;
    total_qty?: number;
    confidence?: number;
    [key: string]: any;
  };
}

interface OrderDetail extends OrderSummary {
  items: OrderItem[];
}

interface DocumentRecord {
  id: string;
  order_id: string;
  filename: string;
  doc_class: string;
  confidence: number;
  size_bytes: number;
  page_count: number;
  uploaded_at: string;
  classification_status: string;
}

interface DocumentListResponse {
  documents: DocumentRecord[];
  total: number;
}

interface HiTLThread {
  thread_id: string;
  order_id: string;
  item_no: string;
  agent_id: string;
  priority: string;
  status: string;
  sla_deadline?: string;
  created_at: string;
}

interface ThreadListResponse {
  threads: HiTLThread[];
  total: number;
}

interface HiTLMessage {
  message_id: string;
  thread_id: string;
  sender_type: string;
  content: string;
  context?: Record<string, any>;
  created_at: string;
}

interface ThreadDetailResponse {
  thread: HiTLThread;
  messages: HiTLMessage[];
}

interface ActivityEntry {
  id: string;
  timestamp: string;
  actor: string;
  actor_type: string;
  action: string;
  detail: string;
}

interface AuditLogResponse {
  entries: ActivityEntry[];
  total: number;
}

/* ── Pipeline stages (matching ItemState enum) ───────────────────────── */

const PIPELINE_STAGES = [
  { key: 'INTAKE_CLASSIFIED', label: 'Intake',     short: 'Int' },
  { key: 'PARSED',           label: 'Parse',      short: 'Par' },
  { key: 'FUSED',            label: 'Fuse',       short: 'Fus' },
  { key: 'COMPLIANCE_EVAL',  label: 'Compliance', short: 'Cmp' },
  { key: 'DRAWING_GENERATED',label: 'Drawings',   short: 'Drw' },
  { key: 'COMPOSED',         label: 'Compose',    short: 'Com' },
  { key: 'VALIDATED',        label: 'Validate',   short: 'Val' },
  { key: 'REVIEWED',         label: 'Review',     short: 'Rev' },
  { key: 'DELIVERED',        label: 'Delivered',  short: 'Del' },
];

const STAGE_ORDER = PIPELINE_STAGES.map(s => s.key);

function stageStatus(
  itemState: string,
  stageKey: string,
  meta?: { last_successful_state?: string; blocked_at_stage?: string },
): 'done' | 'active' | 'blocked' | 'pending' {
  // Resolve the effective "how far did we get" marker. For blocked/failed
  // items the raw state is ``HUMAN_BLOCKED``/``FAILED`` which doesn't
  // say *where* the pipeline got to, so fall back to the last successful
  // stage stashed on the item payload.
  const isBlockedState = itemState === 'HUMAN_BLOCKED' || itemState === 'FAILED';
  const progressState = isBlockedState && meta?.last_successful_state
    ? meta.last_successful_state
    : itemState;
  const currentIdx = STAGE_ORDER.indexOf(progressState);
  const stageIdx = STAGE_ORDER.indexOf(stageKey);

  // If the orchestrator recorded the stage it was blocked on, mark only
  // *that* stage as blocked — earlier ones stay 'done', later ones 'pending'.
  if (isBlockedState && meta?.blocked_at_stage) {
    if (stageKey === meta.blocked_at_stage) return 'blocked';
    if (stageIdx <= currentIdx) return 'done';
    return 'pending';
  }

  // Legacy fallback: terminal-blocked with no hint → paint only the
  // immediately-next stage as blocked rather than every pill.
  if (isBlockedState) {
    if (stageIdx <= currentIdx) return 'done';
    if (stageIdx === currentIdx + 1) return 'blocked';
    return 'pending';
  }

  if (currentIdx < 0) return 'pending';
  if (stageIdx <= currentIdx) return 'done';
  // The very next stage after the latest completed one is the one the
  // pipeline is currently working on — render it with a spinner instead
  // of leaving every non-done stage as a silent dashed circle.
  if (stageIdx === currentIdx + 1) return 'active';
  return 'pending';
}

function StateIcon({ state }: { state: string }) {
  switch (state) {
    case 'done': return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />;
    case 'active': return <Loader2 className="w-3.5 h-3.5 text-blue-500 animate-spin" />;
    case 'blocked': return <AlertCircle className="w-3.5 h-3.5 text-orange-500" />;
    default: return <CircleDashed className="w-3.5 h-3.5 text-gray-300" />;
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ── Order state badge colors ────────────────────────────────────────── */

const STATE_COLORS: Record<string, string> = {
  CREATED: 'bg-gray-100 text-gray-700',
  IN_PROGRESS: 'bg-sky-50 text-sky-700',
  HUMAN_BLOCKED: 'bg-orange-50 text-orange-700',
  READY_TO_DELIVER: 'bg-yellow-50 text-yellow-700',
  ATTENTION: 'bg-red-50 text-red-700',
  DELIVERED: 'bg-emerald-50 text-emerald-700',
};

export default function OrderDetail() {
  const [, params] = useRoute('/orders/:id');
  const [, setLocation] = useLocation();
  const { toast } = useToast();
  const orderId = params?.id || '';

  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [threads, setThreads] = useState<HiTLThread[]>([]);
  const [threadMessages, setThreadMessages] = useState<Record<string, HiTLMessage[]>>({});
  const [activities, setActivities] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);
  const [lastFetchedAt, setLastFetchedAt] = useState<number>(Date.now());
  const [lastStateChangeAt, setLastStateChangeAt] = useState<number>(Date.now());
  const prevItemsKeyRef = React.useRef<string>('');
  const [expandedThreads, setExpandedThreads] = useState<Set<string>>(new Set());
  // Per-thread composer state — the Issues tab is now fully interactive, so
  // each expanded thread carries its own draft and an in-flight flag.
  const [threadDrafts, setThreadDrafts] = useState<Record<string, string>>({});
  const [threadBusy, setThreadBusy] = useState<Record<string, boolean>>({});

  // Live agent-typing indicator for each expanded thread. We only
  // subscribe while the card is open so we don't hold a WS per thread
  // on the whole order page.
  const expandedIds = React.useMemo(
    () => Array.from(expandedThreads),
    [expandedThreads],
  );
  const agentTypingByThread = useAgentTypingByThread(expandedIds);
  // When an agent finishes typing, its reply has just landed — re-pull
  // that thread's messages so the UI updates without waiting for the
  // 15-second order-level poll. We track the previous typing state per
  // thread and only refresh on a true→false transition.
  const prevTypingRef = React.useRef<Record<string, boolean>>({});
  React.useEffect(() => {
    const prev = prevTypingRef.current;
    for (const id of expandedIds) {
      if (prev[id] && !agentTypingByThread[id]) {
        // Fire-and-forget; errors surface through existing toast flows.
        loadThreadMessages(id, { force: true });
      }
    }
    prevTypingRef.current = { ...agentTypingByThread };
    // loadThreadMessages is referentially stable enough for this
    // transition check — intentionally omit from deps.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentTypingByThread, expandedIds]);

  const fetchAll = useCallback(async () => {
    if (!orderId) return;
    setLoading(true);
    setError(null);
    try {
      const [orderData, docsData, hitlData, auditData] = await Promise.all([
        apiGet<OrderDetail>(`/orders/${orderId}`),
        apiGet<DocumentListResponse>(`/documents?order_id=${orderId}`),
        apiGet<ThreadListResponse>('/hitl/threads'),
        apiGet<AuditLogResponse>(`/audit-log?search=${orderId}&limit=10`),
      ]);
      setOrder(orderData);
      setDocuments(docsData.documents);
      // Filter threads by order_id AND hide terminal statuses — the
      // "Issues" tab is a blocker inbox, not an audit log. Leaving
      // RESOLVED / CANCELLED / ESCALATED_RESOLVED threads in the list
      // is what made users think resolving didn't "do anything" — they
      // clicked Resolve, the row flipped status but stayed on screen,
      // and the count next to "Issues (N)" never dropped.
      const TERMINAL_STATUSES = new Set(['RESOLVED', 'CANCELLED']);
      const orderThreads = hitlData.threads.filter(
        t => t.order_id === orderId && !TERMINAL_STATUSES.has(t.status),
      );
      setThreads(orderThreads);
      setActivities(auditData.entries);
      // Track when the pipeline last advanced so we can show a notice
      // if it's been stalled. Compare by a cheap fingerprint of all
      // (item_id, state) pairs so that any single item transition
      // counts as progress.
      const nowTs = Date.now();
      setLastFetchedAt(nowTs);
      const key = (orderData.items ?? [])
        .map((it: any) => `${it.id}:${it.state}`)
        .sort()
        .join('|');
      if (key !== prevItemsKeyRef.current) {
        prevItemsKeyRef.current = key;
        setLastStateChangeAt(nowTs);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load order');
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // Poll faster (5s) while AI is classifying, otherwise every 15s
  const hasClassifying = documents.some(d => d.classification_status === 'classifying');
  useEffect(() => {
    const interval = setInterval(fetchAll, hasClassifying ? 5000 : 15000);
    return () => clearInterval(interval);
  }, [fetchAll, hasClassifying]);

  const loadThreadMessages = async (threadId: string, opts: { force?: boolean } = {}) => {
    if (!opts.force && threadMessages[threadId]) return;
    try {
      const data = await apiGet<ThreadDetailResponse>(`/hitl/threads/${threadId}`);
      setThreadMessages(prev => ({ ...prev, [threadId]: data.messages }));
    } catch {}
  };

  // ── HiTL interactions (reply / option-select / resolve) ─────────────────
  // The Issues tab used to be read-only, so operators had no way to clear
  // an item out of HUMAN_BLOCKED from inside the order page.  These three
  // handlers wrap the same endpoints the dedicated HiTL inbox uses so the
  // unblock flow can happen in context.
  const replyToThread = async (threadId: string) => {
    const content = (threadDrafts[threadId] || '').trim();
    if (!content) return;
    setThreadBusy(prev => ({ ...prev, [threadId]: true }));
    try {
      await apiPost(`/hitl/threads/${threadId}/messages`, {
        sender_type: 'human',
        content,
      });
      setThreadDrafts(prev => ({ ...prev, [threadId]: '' }));
      await loadThreadMessages(threadId, { force: true });
      toast({ title: 'Reply sent' });
    } catch (e: any) {
      toast({ title: 'Reply failed', description: e?.message || String(e), variant: 'destructive' });
    } finally {
      setThreadBusy(prev => ({ ...prev, [threadId]: false }));
    }
  };

  const selectThreadOption = async (
    threadId: string,
    optionIndex: number,
    optionValue: string,
  ) => {
    setThreadBusy(prev => ({ ...prev, [threadId]: true }));
    try {
      await apiPost(`/hitl/threads/${threadId}/option-select`, {
        option_index: optionIndex,
        option_value: optionValue,
      });
      await loadThreadMessages(threadId, { force: true });
      toast({ title: 'Option selected', description: optionValue });
    } catch (e: any) {
      toast({ title: 'Option-select failed', description: e?.message || String(e), variant: 'destructive' });
    } finally {
      setThreadBusy(prev => ({ ...prev, [threadId]: false }));
    }
  };

  const resolveThreadAction = async (threadId: string) => {
    setThreadBusy(prev => ({ ...prev, [threadId]: true }));
    try {
      await apiPost(`/hitl/threads/${threadId}/resolve`, {
        note: 'Resolved from order page',
      });
      await loadThreadMessages(threadId, { force: true });
      await fetchAll();
      toast({
        title: 'Thread resolved',
        description: 'Click "Advance pipeline" to retry the blocked stage.',
      });
    } catch (e: any) {
      toast({ title: 'Resolve failed', description: e?.message || String(e), variant: 'destructive' });
    } finally {
      setThreadBusy(prev => ({ ...prev, [threadId]: false }));
    }
  };

  // The agent's most recent message can carry a list of options the operator
  // is meant to pick from, e.g. ``context: { options: ["Use 25.4mm", "Skip"] }``.
  // We surface those as buttons above the free-text composer.
  const extractOptions = (messages: HiTLMessage[] | undefined): string[] => {
    if (!messages || messages.length === 0) return [];
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.sender_type !== 'agent') continue;
      const opts = m.context?.options;
      if (Array.isArray(opts) && opts.every(o => typeof o === 'string')) {
        return opts as string[];
      }
      break; // only consider the latest agent prompt
    }
    return [];
  };

  if (loading && !order) {
    return (
      <div className="p-6 flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading order...</span>
      </div>
    );
  }

  if (error && !order) {
    return (
      <div className="p-6 text-center">
        <p className="text-red-600">{error}</p>
        <Button variant="link" onClick={() => setLocation('/orders')}>Back to Orders</Button>
      </div>
    );
  }

  if (!order) {
    return (
      <div className="p-6 text-center">
        <p className="text-muted-foreground">Order not found</p>
        <Button variant="link" onClick={() => setLocation('/orders')}>Back to Orders</Button>
      </div>
    );
  }

  const stateColor = STATE_COLORS[order.state] || STATE_COLORS.CREATED;

  return (
    <div className="flex flex-col h-[calc(100vh-56px)]">
      {/* Header */}
      <div className="px-6 pt-4 pb-3 border-b shrink-0 bg-card z-10 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setLocation('/orders')}>
              <ArrowLeft className="w-4 h-4" />
            </Button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold font-mono tracking-tight">{order.po_number}</h1>
                <Badge variant="outline" className={`text-xs ${stateColor}`}>
                  {order.state.replace(/_/g, ' ')}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {order.importer_id} · {order.item_count} items · {order.id}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={fetchAll}>
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </Button>
            <Button variant="outline" size="sm" disabled={mutating} onClick={async () => {
              toast({ title: 'Download started', description: 'Preparing ZIP...' });
              try {
                await apiGet(`/orders/${orderId}/items`);
              } catch {}
            }}>
              <Download className="w-3.5 h-3.5 mr-1.5" /> Download All
            </Button>
            <Button variant="outline" size="sm" disabled={mutating} onClick={async () => {
              setMutating(true);
              try {
                await apiPost(`/orders/${orderId}/send-to-printer`);
                toast({ title: 'Sent to printer' });
                await fetchAll();
              } catch (e: any) {
                toast({ title: 'Error', description: e.message || 'Failed to send to printer', variant: 'destructive' });
              } finally {
                setMutating(false);
              }
            }}>
              <Printer className="w-3.5 h-3.5 mr-1.5" /> Send to Printer
            </Button>
            {order.state === 'READY_TO_DELIVER' && (
              <Button size="sm" disabled={mutating} onClick={async () => {
                setMutating(true);
                try {
                  await apiPost(`/orders/${orderId}/approve`);
                  toast({ title: 'Approved', description: 'Approval PDFs sent.' });
                  await fetchAll();
                } catch (e: any) {
                  toast({ title: 'Error', description: e.message || 'Failed to approve', variant: 'destructive' });
                } finally {
                  setMutating(false);
                }
              }}>
                <Send className="w-3.5 h-3.5 mr-1.5" /> Approve & Send
              </Button>
            )}
          </div>
        </div>

        {/* Pipeline tracker for first item */}
        {order.items.length > 0 && (
          <div className="flex items-center gap-0.5">
            {PIPELINE_STAGES.map((stage, i) => {
              // Use the most advanced item state to show overall pipeline progress
              const firstItem = order.items[0];
              const meta = (firstItem.data ?? {}) as {
                last_successful_state?: string;
                blocked_at_stage?: string;
              };
              const status = stageStatus(firstItem.state, stage.key, meta);
              return (
                <React.Fragment key={stage.key}>
                  <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors
                    ${status === 'done' ? 'bg-emerald-50 text-emerald-700' : ''}
                    ${status === 'active' ? 'bg-primary/10 text-primary ring-1 ring-primary/30' : ''}
                    ${status === 'blocked' ? 'bg-orange-50 text-orange-700 ring-1 ring-orange-300' : ''}
                    ${status === 'pending' ? 'bg-muted text-muted-foreground' : ''}
                  `}>
                    {status === 'done' && <CheckCircle2 className="w-3 h-3" />}
                    {status === 'active' && <Loader2 className="w-3 h-3 animate-spin" />}
                    {status === 'blocked' && <Pause className="w-3 h-3" />}
                    {status === 'pending' && <CircleDashed className="w-3 h-3" />}
                    <span className="hidden lg:inline">{stage.label}</span>
                  </div>
                  {i < PIPELINE_STAGES.length - 1 && (
                    <ChevronRight className={`w-3 h-3 shrink-0 ${status === 'done' ? 'text-emerald-400' : 'text-muted-foreground/30'}`} />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        )}

        {/* Live progress notice — surfaces when the pipeline is mid-stage
            and whether it has stalled. Without this the order page looks
            frozen while an async worker is crunching away. */}
        {order.items.length > 0 && (() => {
          const itemState = order.items[0].state;
          const TERMINAL = new Set(['DELIVERED', 'FAILED', 'HUMAN_BLOCKED']);
          if (TERMINAL.has(itemState)) return null;
          const currentIdx = STAGE_ORDER.indexOf(itemState);
          const nextStage = currentIdx >= 0 && currentIdx + 1 < PIPELINE_STAGES.length
            ? PIPELINE_STAGES[currentIdx + 1]
            : null;
          const stalledSec = Math.floor((lastFetchedAt - lastStateChangeAt) / 1000);
          const isStalled = stalledSec > 45;
          if (!nextStage) return null;
          return (
            <div className={`mt-2 flex items-center gap-2 text-xs ${
              isStalled ? 'text-orange-700' : 'text-muted-foreground'
            }`}>
              {isStalled ? (
                <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
              ) : (
                <Loader2 className="w-3.5 h-3.5 shrink-0 animate-spin text-primary" />
              )}
              <span>
                {isStalled ? (
                  <>
                    Waiting on <strong>{nextStage.label}</strong> for {stalledSec}s — the
                    orchestrator worker may not be running.
                  </>
                ) : (
                  <>
                    Running <strong>{nextStage.label}</strong> stage · polling every{' '}
                    {hasClassifying ? '5' : '15'} s
                  </>
                )}
              </span>
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs"
                onClick={() => fetchAll()}
              >
                Refresh now
              </Button>
              {isStalled && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  disabled={mutating}
                  onClick={async () => {
                    setMutating(true);
                    try {
                      // force=true: operator explicitly asked to retry — run the
                      // full _STAGE_PLAN cascade after rescue. The auto-advance
                      // hook that fires on HiTL Resolve uses the default
                      // (force=false) so it only rescues, never auto-re-
                      // validates (which would just re-spawn the same thread).
                      const res = await apiPost<{ ran_steps: Array<{ stage: string; items_advanced: number; needs_hitl: number; failed: number }>; stalled_reason?: string | null }>(`/orders/${orderId}/advance?force=true`);
                      const summary = res.ran_steps
                        .map(s => `${s.stage} +${s.items_advanced}${s.needs_hitl ? ` (${s.needs_hitl} HITL)` : ''}`)
                        .join(' · ') || 'no stage to run';
                      toast({
                        title: 'Pipeline advanced',
                        description: res.stalled_reason ? `${summary} — stalled: ${res.stalled_reason}` : summary,
                      });
                      await fetchAll();
                    } catch (e: any) {
                      toast({ title: 'Advance failed', description: e.message || String(e), variant: 'destructive' });
                    } finally {
                      setMutating(false);
                    }
                  }}
                >
                  {mutating ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
                  Advance pipeline
                </Button>
              )}
            </div>
          );
        })()}
      </div>

      {/* Tabs + Activity sidebar */}
      <div className="flex-1 overflow-hidden flex">
        {/* Main content with tabs */}
        <div className="flex-1 overflow-hidden flex flex-col">
        <Tabs defaultValue="items" className="flex-1 flex flex-col">
          <div className="px-6 pt-3 shrink-0 border-b bg-background">
            <TabsList>
              <TabsTrigger value="items">Items ({order.items.length})</TabsTrigger>
              <TabsTrigger value="documents">Documents ({documents.length})</TabsTrigger>
              <TabsTrigger value="issues">Issues ({threads.length})</TabsTrigger>
              <TabsTrigger value="review">Review</TabsTrigger>
            </TabsList>
          </div>

          <div className="flex-1 overflow-auto">
            {/* Items Tab */}
            <TabsContent value="items" className="m-0 p-0 h-full">
              <div className="overflow-auto h-full">
                <Table>
                  <TableHeader className="bg-muted/40 sticky top-0 z-10">
                    <TableRow>
                      <TableHead className="w-[80px]">Item #</TableHead>
                      <TableHead className="min-w-[200px]">Description</TableHead>
                      <TableHead className="w-[100px]">UPC</TableHead>
                      <TableHead className="w-[60px] text-center">Qty</TableHead>
                      <TableHead className="w-[100px]">State</TableHead>
                      {PIPELINE_STAGES.map(s => (
                        <TableHead key={s.key} className="text-center w-[40px] px-1" title={s.label}>
                          <span className="text-[10px]">{s.short}</span>
                        </TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {order.items.map(item => (
                      <TableRow key={item.id} className="hover:bg-muted/30 cursor-pointer" onClick={() => setLocation(`/orders/${orderId}/items/${item.id}`)}>
                        <TableCell className="font-mono text-xs font-medium text-primary">{item.item_no}</TableCell>
                        <TableCell className="text-xs max-w-[250px] truncate" title={item.data?.description || ''}>
                          {item.data?.description || <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell className="font-mono text-[10px] text-muted-foreground">{item.data?.upc || '—'}</TableCell>
                        <TableCell className="text-xs text-center tabular-nums">{item.data?.total_qty ?? item.data?.case_qty ?? '—'}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="text-[10px]">
                            {item.state.replace(/_/g, ' ')}
                          </Badge>
                        </TableCell>
                        {PIPELINE_STAGES.map(s => (
                          <TableCell key={s.key} className="text-center p-0">
                            <div className="flex items-center justify-center h-10">
                              <StateIcon state={stageStatus(
                                item.state,
                                s.key,
                                (item.data ?? {}) as { last_successful_state?: string; blocked_at_stage?: string },
                              )} />
                            </div>
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                    {order.items.length === 0 && (
                      <TableRow>
                        <TableCell colSpan={15} className="text-center py-12 text-muted-foreground">
                          No items in this order yet. Upload a PO or PI document to extract items automatically.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </TabsContent>

            {/* Documents Tab */}
            <TabsContent value="documents" className="m-0 p-6">
              <div className="grid gap-3 max-w-2xl">
                {documents.length === 0 && (
                  <div className="text-center py-12 text-muted-foreground border rounded-md border-dashed">
                    No documents uploaded for this order.
                  </div>
                )}
                {documents.map(doc => (
                  <div key={doc.id} className="flex items-center justify-between p-3 border rounded-md hover:bg-muted/30 transition-colors">
                    <div className="flex items-center gap-3">
                      {doc.filename.endsWith('.xlsx') || doc.filename.endsWith('.xls')
                        ? <FileSpreadsheet className="w-5 h-5 text-green-600" />
                        : <FileText className="w-5 h-5 text-blue-600" />
                      }
                      <div>
                        <div className="text-sm font-medium">{doc.filename}</div>
                        <div className="text-xs text-muted-foreground">
                          {doc.doc_class.replace(/_/g, ' ')} · {formatBytes(doc.size_bytes)}
                          {doc.confidence > 0 && (
                            <span className={`ml-1 ${doc.confidence >= 0.9 ? 'text-green-600' : doc.confidence >= 0.7 ? 'text-amber-600' : 'text-red-600'}`}>
                              · {(doc.confidence * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {doc.classification_status === 'classifying' ? (
                        <Badge variant="outline" className="text-[10px] bg-blue-50 text-blue-700 border-blue-200 animate-pulse">
                          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                          AI classifying
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px]">{doc.classification_status}</Badge>
                      )}
                      <Button variant="ghost" size="sm" onClick={() => {
                        const authData = JSON.parse(localStorage.getItem('auth-storage') || '{}');
                        const token = authData?.state?.accessToken || '';
                        window.open(`/api/v1/documents/${doc.id}/preview?token=${token}`, '_blank');
                      }}>
                        <Eye className="w-3.5 h-3.5 mr-1" /> Preview
                      </Button>
                      <Button variant="ghost" size="sm" onClick={async () => {
                        try {
                          const authData = JSON.parse(localStorage.getItem('auth-storage') || '{}');
                          const token = authData?.state?.accessToken || '';
                          const response = await fetch(`/api/v1/documents/${doc.id}/preview`, {
                            headers: { 'Authorization': `Bearer ${token}` },
                          });
                          if (!response.ok) throw new Error('Download failed');
                          const blob = await response.blob();
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement('a');
                          a.href = url;
                          a.download = doc.filename;
                          document.body.appendChild(a);
                          a.click();
                          a.remove();
                          URL.revokeObjectURL(url);
                        } catch {
                          toast({ title: 'Download failed', variant: 'destructive' });
                        }
                      }}>
                        <Download className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>

            {/* Issues Tab */}
            <TabsContent value="issues" className="m-0 p-6">
              <div className="space-y-3 max-w-2xl">
                {threads.length === 0 && (
                  <div className="text-center py-12 text-muted-foreground border rounded-md border-dashed">
                    <CheckCircle2 className="w-8 h-8 mx-auto mb-2 text-emerald-400" />
                    No blocking issues.
                  </div>
                )}
                {threads.map(thread => {
                  const isExpanded = expandedThreads.has(thread.thread_id);
                  const messages = threadMessages[thread.thread_id];
                  return (
                    <Card
                      key={thread.thread_id}
                      className="cursor-pointer hover:border-primary/50 transition-colors"
                      onClick={() => {
                        loadThreadMessages(thread.thread_id);
                        setExpandedThreads(prev => {
                          const next = new Set(prev);
                          if (next.has(thread.thread_id)) {
                            next.delete(thread.thread_id);
                          } else {
                            next.add(thread.thread_id);
                          }
                          return next;
                        });
                      }}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex items-start gap-3">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 mt-0.5
                              ${thread.status === 'RESOLVED' ? 'bg-emerald-100 text-emerald-600' : thread.status === 'OPEN' ? 'bg-orange-100 text-orange-600' : 'bg-gray-100 text-gray-500'}`}>
                              {thread.status === 'RESOLVED' ? <CheckCircle2 className="w-4 h-4" /> : <MessageSquare className="w-4 h-4" />}
                            </div>
                            <div>
                              <div className="text-sm font-medium">
                                {thread.agent_id} — Item {thread.item_no}
                              </div>
                              <div className="text-xs text-muted-foreground mt-0.5">
                                Priority: {thread.priority} · Status: {thread.status}
                                {thread.sla_deadline && (
                                  <span className="ml-1">· SLA: {new Date(thread.sla_deadline).toLocaleDateString('en-IN', { day: '2-digit', month: 'short' })}</span>
                                )}
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge variant="outline" className={`text-xs ${
                              thread.status === 'RESOLVED' ? 'bg-emerald-50 text-emerald-700' :
                              thread.status === 'OPEN' ? 'bg-orange-50 text-orange-700' : 'bg-sky-50 text-sky-700'
                            }`}>{thread.status}</Badge>
                            <ChevronRight className={`w-4 h-4 text-muted-foreground transition-transform ${isExpanded ? 'rotate-90' : ''}`} />
                          </div>
                        </div>
                        {isExpanded && (
                          <div className="mt-3 pt-3 border-t space-y-2" onClick={e => e.stopPropagation()}>
                            {!messages && (
                              <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground">
                                <Loader2 className="w-3 h-3 animate-spin" /> Loading messages...
                              </div>
                            )}
                            {messages && messages.length === 0 && (
                              <p className="text-xs text-muted-foreground py-2">No messages yet.</p>
                            )}
                            {messages && messages.map(msg => (
                              <div
                                key={msg.message_id}
                                className={`flex ${msg.sender_type === 'agent' ? 'justify-start' : 'justify-end'}`}
                              >
                                <div className={`max-w-[80%] rounded-lg px-3 py-2 text-xs ${
                                  msg.sender_type === 'agent'
                                    ? 'bg-muted text-foreground'
                                    : 'bg-primary text-primary-foreground'
                                }`}>
                                  <div className="font-medium mb-0.5 text-[10px] opacity-70">{msg.sender_type}</div>
                                  <div>{msg.content}</div>
                                  <div className="text-[10px] opacity-50 mt-1">
                                    {new Date(msg.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                  </div>
                                </div>
                              </div>
                            ))}
                            {agentTypingByThread[thread.thread_id] && (
                              <div className="flex justify-start" role="status" aria-live="polite">
                                <div className="max-w-[80%] rounded-lg px-3 py-2 text-xs bg-muted text-foreground">
                                  <div className="font-medium mb-0.5 text-[10px] opacity-70">
                                    {thread.agent_id}
                                  </div>
                                  <div className="flex items-center gap-1 h-4" aria-label={`${thread.agent_id} is typing`}>
                                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce" style={{ animationDelay: '0ms' }} />
                                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce" style={{ animationDelay: '150ms' }} />
                                    <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce" style={{ animationDelay: '300ms' }} />
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Reply composer / option-select / resolve — only
                                meaningful while the thread is still open. */}
                            {messages && thread.status !== 'RESOLVED' && (
                              <div className="mt-3 pt-3 border-t space-y-2">
                                {(() => {
                                  const options = extractOptions(messages);
                                  if (options.length === 0) return null;
                                  return (
                                    <div className="flex flex-wrap gap-1.5">
                                      <span className="text-[10px] text-muted-foreground self-center mr-1">
                                        Pick one:
                                      </span>
                                      {options.map((opt, idx) => (
                                        <Button
                                          key={`${idx}-${opt}`}
                                          size="sm"
                                          variant="outline"
                                          className="h-7 text-xs"
                                          disabled={!!threadBusy[thread.thread_id]}
                                          onClick={() => selectThreadOption(thread.thread_id, idx, opt)}
                                        >
                                          {opt}
                                        </Button>
                                      ))}
                                    </div>
                                  );
                                })()}
                                <Textarea
                                  value={threadDrafts[thread.thread_id] || ''}
                                  onChange={e => setThreadDrafts(prev => ({
                                    ...prev,
                                    [thread.thread_id]: e.target.value,
                                  }))}
                                  placeholder="Reply to the agent… (Shift+Enter for newline, Enter to send)"
                                  className="text-xs min-h-[60px]"
                                  disabled={!!threadBusy[thread.thread_id]}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter' && !e.shiftKey) {
                                      e.preventDefault();
                                      replyToThread(thread.thread_id);
                                    }
                                  }}
                                />
                                <div className="flex items-center justify-between gap-2">
                                  <Button
                                    size="sm"
                                    className="h-7 text-xs"
                                    disabled={!!threadBusy[thread.thread_id] || !(threadDrafts[thread.thread_id] || '').trim()}
                                    onClick={() => replyToThread(thread.thread_id)}
                                  >
                                    {threadBusy[thread.thread_id]
                                      ? <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                                      : <Send className="w-3 h-3 mr-1" />}
                                    Send reply
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    className="h-7 text-xs"
                                    disabled={!!threadBusy[thread.thread_id]}
                                    onClick={() => resolveThreadAction(thread.thread_id)}
                                  >
                                    <CheckCheck className="w-3 h-3 mr-1" /> Resolve
                                  </Button>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </TabsContent>

            {/* Review Tab */}
            <TabsContent value="review" className="m-0 p-6">
              <div className="max-w-2xl space-y-4">
                {order.state === 'READY_TO_DELIVER' ? (
                  <>
                    <Card className="border-yellow-200 bg-yellow-50/30">
                      <CardContent className="p-4">
                        <div className="flex items-start gap-3">
                          <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5" />
                          <div>
                            <div className="font-medium text-sm">Awaiting your review</div>
                            <p className="text-xs text-muted-foreground mt-1">
                              All {order.items.length} items have been processed. Review and approve to send to the client.
                            </p>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    <div className="flex gap-2">
                      <Button disabled={mutating} onClick={async () => {
                        setMutating(true);
                        try {
                          await apiPost(`/orders/${orderId}/approve`);
                          toast({ title: 'Approved', description: 'Sending approval PDFs...' });
                          await fetchAll();
                        } catch (e: any) {
                          toast({ title: 'Error', description: e.message || 'Failed to approve', variant: 'destructive' });
                        } finally {
                          setMutating(false);
                        }
                      }}>
                        <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approve All & Send
                      </Button>
                      <Button variant="outline" disabled={mutating} onClick={async () => {
                        setMutating(true);
                        try {
                          await apiPost(`/orders/${orderId}/reject`, { reason: 'Sent back for rework' });
                          toast({ title: 'Rejected', description: 'Sent back for rework.' });
                          await fetchAll();
                        } catch (e: any) {
                          toast({ title: 'Error', description: e.message || 'Failed to reject', variant: 'destructive' });
                        } finally {
                          setMutating(false);
                        }
                      }}>
                        <XCircle className="w-4 h-4 mr-1.5" /> Reject & Loop Back
                      </Button>
                    </div>
                  </>
                ) : order.state === 'DELIVERED' ? (
                  <Card className="border-emerald-200 bg-emerald-50/30">
                    <CardContent className="p-4">
                      <div className="flex items-center gap-3">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        <div>
                          <div className="font-medium text-sm">Delivered</div>
                          <p className="text-xs text-muted-foreground mt-1">
                            All items approved and delivered.
                          </p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="text-center py-12 text-muted-foreground border rounded-md border-dashed">
                    Pipeline not yet at review stage. Current state: {order.state.replace(/_/g, ' ')}.
                  </div>
                )}
              </div>
            </TabsContent>
          </div>
        </Tabs>
        </div>

        {/* Activity sidebar */}
        <div className="w-72 border-l overflow-auto shrink-0 hidden lg:block">
          <div className="p-4">
            <h3 className="text-sm font-semibold mb-3">Activity</h3>
            <div className="space-y-3">
              {activities.map(entry => (
                <div key={entry.id} className="flex gap-2.5">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs shrink-0 mt-0.5 ${entry.actor_type === 'agent' ? 'bg-primary/10 text-primary' : 'bg-orange-100 text-orange-600'}`}>
                    {entry.actor_type === 'agent' ? <Bot className="w-3 h-3" /> : <User className="w-3 h-3" />}
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs leading-snug">
                      <span className="font-medium">{entry.actor}</span>{' '}
                      <span className="text-muted-foreground">{entry.detail}</span>
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {new Date(entry.timestamp).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              ))}
              {activities.length === 0 && (
                <p className="text-xs text-muted-foreground text-center py-4">No activity yet.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
