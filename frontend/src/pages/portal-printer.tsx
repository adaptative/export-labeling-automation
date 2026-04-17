import React, { useCallback, useEffect, useState } from 'react';
import { useRoute } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import {
  Download,
  CheckCircle2,
  Package,
  Printer,
  AlertCircle,
  FileText,
  ClipboardCheck,
  Loader2,
  XCircle,
  Clock,
} from 'lucide-react';
import {
  PortalApiError,
  PortalSessionResponse,
  confirmPrinter,
  getPrinterItemBundle,
  getPrinterSession,
} from '../api/portal';

type UiStatus = 'loading' | 'active' | 'confirmed' | 'expired' | 'invalid' | 'error';

export default function PortalPrinter() {
  const [, params] = useRoute('/portal/printer/:token');
  const token = params?.token || '';
  const { toast } = useToast();

  const [session, setSession] = useState<PortalSessionResponse | null>(null);
  const [uiStatus, setUiStatus] = useState<UiStatus>('loading');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [downloadedItems, setDownloadedItems] = useState<Set<string>>(new Set());
  const [printerName, setPrinterName] = useState('');
  const [printerEmail, setPrinterEmail] = useState('');
  const [printerNote, setPrinterNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);

  const mapStatus = (status: string): UiStatus =>
    status === 'active' ? 'active' :
    status === 'confirmed' ? 'confirmed' :
    'active';

  const loadSession = useCallback(async () => {
    if (!token) {
      setUiStatus('invalid');
      setErrorMessage('No portal token provided.');
      return;
    }
    setUiStatus('loading');
    setErrorMessage(null);
    try {
      const data = await getPrinterSession(token);
      setSession(data);
      setUiStatus(mapStatus(data.status));
    } catch (e) {
      if (e instanceof PortalApiError) {
        if (e.status === 404) {
          setUiStatus('invalid');
          setErrorMessage('This portal link is invalid or has been revoked.');
        } else if (e.status === 410) {
          setUiStatus('expired');
          setErrorMessage('This portal link has expired. Please request a new one.');
        } else {
          setUiStatus('error');
          setErrorMessage(e.message);
        }
      } else {
        setUiStatus('error');
        setErrorMessage(e instanceof Error ? e.message : 'Failed to load session');
      }
    }
  }, [token]);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  const handleDownloadBundle = async (itemId: string, itemNo: string) => {
    setDownloading(itemId);
    try {
      const bundle = await getPrinterItemBundle(token, itemId);
      if (bundle.kind === 'missing') {
        toast({
          title: 'Bundle not ready',
          description: bundle.detail ||
            (bundle.reason === 'blob_missing'
              ? 'The bundle record exists but the ZIP is missing from storage.'
              : 'The printer bundle has not been generated yet.'),
        });
        return;
      }
      const poNumber = session?.order?.po_number || 'order';
      const a = document.createElement('a');
      a.href = bundle.url;
      a.download = `${poNumber}_${itemNo}_bundle.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoke the blob URL after a short delay (Chrome/Firefox need the link to complete).
      setTimeout(() => URL.revokeObjectURL(bundle.url), 10_000);
      setDownloadedItems(prev => new Set([...prev, itemId]));
      toast({ title: 'Download started', description: `${itemNo}_bundle.zip` });
    } catch (e) {
      toast({
        title: 'Download failed',
        description: e instanceof Error ? e.message : 'Unknown error',
        variant: 'destructive' as any,
      });
    } finally {
      setDownloading(null);
    }
  };

  const handleDownloadAll = async () => {
    if (!session) return;
    for (const it of session.items) {
      await handleDownloadBundle(it.id, it.item_no);
    }
  };

  const handleConfirm = async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const result = await confirmPrinter(token, {
        printer_name: printerName || undefined,
        printer_email: printerEmail || undefined,
        note: printerNote || undefined,
      });
      toast({
        title: 'Print job confirmed',
        description: result.message || 'Nakoda Art & Craft has been notified.',
      });
      await loadSession();
    } catch (e) {
      if (e instanceof PortalApiError && e.status === 409) {
        toast({
          title: 'Already confirmed',
          description: 'This portal link has already been used.',
        });
        await loadSession();
      } else {
        toast({
          title: 'Confirmation failed',
          description: e instanceof Error ? e.message : 'Unknown error',
          variant: 'destructive' as any,
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ── Header + error / loading states ───────────────────────────────────
  const jobLabel = session?.order?.po_number || session?.order?.id?.slice(0, 10) || token.slice(0, 10);
  const header = (
    <header className="border-b bg-card h-14 flex items-center justify-between px-6 sticky top-0 z-10">
      <div className="flex items-center gap-3">
        <span className="font-mono font-bold text-primary text-lg tracking-tight">Labelforge</span>
        <span className="text-muted-foreground text-sm">· Printer Handoff Portal</span>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant="outline" className="text-xs font-mono">{jobLabel}</Badge>
        <div className="w-2 h-2 rounded-full bg-green-500" />
        <span className="text-xs text-muted-foreground">Secure</span>
      </div>
    </header>
  );

  if (uiStatus === 'loading') {
    return (
      <div className="min-h-screen bg-background text-foreground">
        {header}
        <div className="max-w-3xl mx-auto py-24 px-6 flex flex-col items-center text-muted-foreground">
          <Loader2 className="w-6 h-6 animate-spin" />
          <p className="text-sm mt-3">Loading print job…</p>
        </div>
      </div>
    );
  }

  if (uiStatus === 'invalid' || uiStatus === 'expired' || uiStatus === 'error') {
    const title =
      uiStatus === 'expired' ? 'Link expired' :
      uiStatus === 'invalid' ? 'Link not recognised' :
      'Something went wrong';
    const IconC = uiStatus === 'error' ? AlertCircle : XCircle;
    return (
      <div className="min-h-screen bg-background text-foreground">
        {header}
        <div className="max-w-md mx-auto py-16 px-6 text-center space-y-4">
          <div className="flex justify-center">
            <div className="w-16 h-16 rounded-full bg-red-100 flex items-center justify-center">
              <IconC className="w-8 h-8 text-red-600" />
            </div>
          </div>
          <h2 className="text-xl font-bold">{title}</h2>
          <p className="text-sm text-muted-foreground">{errorMessage}</p>
          <p className="text-xs text-muted-foreground">
            Contact Nakoda Art & Craft to request a new handoff link.
          </p>
        </div>
      </div>
    );
  }

  const order = session?.order;
  const items = session?.items || [];
  const downloadedCount = downloadedItems.size;
  const totalItems = items.length;
  const progressPct = totalItems === 0 ? 0 : Math.round((downloadedCount / totalItems) * 100);
  const isConfirmed = uiStatus === 'confirmed';

  return (
    <div className="min-h-screen bg-background text-foreground">
      {header}

      <div className="max-w-3xl mx-auto py-10 px-6 space-y-8">
        {/* Job summary */}
        <div className="border rounded-xl p-6 bg-card">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Printer className="w-6 h-6 text-primary" />
            </div>
            <div className="flex-1">
              <h1 className="text-xl font-bold">Print Job {order?.po_number || order?.id}</h1>
              <p className="text-sm text-muted-foreground mt-1">
                Labels for <strong className="text-foreground">
                  {session?.importer?.name || 'importer'}
                </strong>
                {order?.po_number ? <> — PO <span className="font-mono">{order.po_number}</span></> : null}
              </p>
            </div>
            <Badge variant="outline" className={`text-xs ${isConfirmed ? 'bg-green-100 text-green-700 border-green-200' : 'bg-yellow-100 text-yellow-700 border-yellow-200'}`}>
              {isConfirmed ? 'Confirmed' : 'Awaiting confirmation'}
            </Badge>
          </div>

          <div className="grid grid-cols-3 gap-4 mt-6 text-sm">
            <div>
              <p className="text-muted-foreground text-xs">Items</p>
              <p className="font-bold font-mono tabular-nums text-lg mt-0.5">{totalItems}</p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Downloaded</p>
              <p className="font-bold font-mono tabular-nums text-lg mt-0.5">
                {downloadedCount}/{totalItems}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground text-xs">Expires</p>
              <p className="font-bold text-lg mt-0.5">
                {session?.expires_at
                  ? new Date(session.expires_at).toLocaleDateString('en-US', { dateStyle: 'medium' })
                  : '—'}
              </p>
            </div>
          </div>

          {!isConfirmed && totalItems > 0 && (
            <div className="mt-4">
              <div className="flex justify-between text-xs mb-1">
                <span className="text-muted-foreground">Download progress</span>
                <span className="font-mono">{progressPct}%</span>
              </div>
              <Progress value={progressPct} className="h-2" />
            </div>
          )}
        </div>

        {/* Item list */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-sm flex items-center gap-2">
              <FileText className="w-4 h-4" /> Label Bundles
            </h2>
            {!isConfirmed && totalItems > 0 && (
              <Button size="sm" onClick={handleDownloadAll} disabled={!!downloading}>
                <Download className="w-3.5 h-3.5 mr-1.5" /> Download All
              </Button>
            )}
          </div>
          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No items attached to this order.
            </p>
          ) : (
            items.map((it) => {
              const isDownloaded = downloadedItems.has(it.id);
              const isDownloading = downloading === it.id;
              return (
                <div key={it.id} className="flex items-center gap-3 p-4 border rounded-lg bg-card text-sm">
                  <Package className="w-4 h-4 text-muted-foreground shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{it.item_no}</span>
                      <Badge variant="secondary" className="text-xs">{it.state}</Badge>
                    </div>
                    <div className="font-medium mt-0.5 truncate text-xs text-muted-foreground">
                      ID: {it.id}
                    </div>
                  </div>
                  {isDownloading ? (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" /> Downloading…
                    </div>
                  ) : isDownloaded ? (
                    <div className="flex items-center gap-2 text-xs text-green-600">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Downloaded
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleDownloadBundle(it.id, it.item_no)}
                      disabled={isConfirmed}
                    >
                      <Download className="w-3.5 h-3.5 mr-1.5" /> Bundle
                    </Button>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Order meta */}
        <div className="border rounded-xl overflow-hidden">
          <div className="px-4 py-3 bg-muted/50 border-b text-sm font-semibold">Order Details</div>
          <div className="p-4 grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">PO Number</span>
              <div className="font-medium mt-1 font-mono">{order?.po_number || '—'}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Order ID</span>
              <div className="font-medium mt-1 font-mono text-xs truncate">{order?.id}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Importer</span>
              <div className="font-medium mt-1">{session?.importer?.name || '—'}</div>
            </div>
            <div>
              <span className="text-muted-foreground">Importer Code</span>
              <div className="font-medium mt-1 font-mono">{session?.importer?.code || '—'}</div>
            </div>
          </div>
        </div>

        {/* Confirm receipt */}
        {isConfirmed ? (
          <div className="flex items-start gap-3 border border-green-200 bg-green-50 rounded-xl p-5">
            <CheckCircle2 className="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold text-green-800">Print job confirmed</p>
              <p className="text-xs text-green-700 mt-0.5">
                Confirmed {session?.action_taken_at
                  ? `on ${new Date(session.action_taken_at).toLocaleString()}`
                  : ''}. Nakoda Art & Craft has been notified.
              </p>
            </div>
          </div>
        ) : (
          <div className="border rounded-xl p-6 bg-card space-y-4">
            <h3 className="font-semibold flex items-center gap-2">
              <ClipboardCheck className="w-4 h-4" /> Confirm Receipt
            </h3>
            <p className="text-sm text-muted-foreground">
              Once you have downloaded and reviewed all label bundles, confirm receipt below.
              This notifies <strong className="text-foreground">Nakoda Art & Craft</strong> that
              the job is in production.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Printer / operator name</label>
                <input
                  type="text"
                  className="w-full mt-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={printerName}
                  onChange={(e) => setPrinterName(e.target.value)}
                  placeholder="e.g. PressBot Operator"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Email (optional)</label>
                <input
                  type="email"
                  className="w-full mt-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={printerEmail}
                  onChange={(e) => setPrinterEmail(e.target.value)}
                  placeholder="press@shop.com"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-muted-foreground">Note (optional)</label>
              <textarea
                className="w-full mt-1 h-20 rounded-lg border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                value={printerNote}
                onChange={(e) => setPrinterNote(e.target.value)}
                placeholder="Any notes about receipt or print setup…"
              />
            </div>

            {downloadedCount < totalItems && totalItems > 0 && (
              <div className="flex items-start gap-2 text-xs text-orange-700 bg-orange-50 border border-orange-200 rounded-lg p-3">
                <Clock className="w-4 h-4 shrink-0 mt-0.5" />
                <span>
                  You have downloaded {downloadedCount} of {totalItems} bundles.
                  You can still confirm — re-downloads remain available until the link expires.
                </span>
              </div>
            )}

            <Button onClick={handleConfirm} className="w-full" disabled={submitting}>
              {submitting
                ? <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                : <CheckCircle2 className="w-4 h-4 mr-2" />}
              Confirm Print Job Receipt
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
