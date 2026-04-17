import React, { useCallback, useEffect, useState } from 'react';
import { useRoute } from 'wouter';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { useToast } from '@/hooks/use-toast';
import {
  CheckCircle2,
  Tag,
  AlertCircle,
  Package,
  ThumbsUp,
  ThumbsDown,
  Building2,
  Globe,
  Shield,
  Loader2,
  XCircle,
  Clock,
} from 'lucide-react';
import {
  PortalApiError,
  PortalSessionResponse,
  approveImporter,
  getImporterSession,
  rejectImporter,
} from '../api/portal';

type UiStatus = 'loading' | 'active' | 'approved' | 'rejected' | 'expired' | 'invalid' | 'error';

export default function PortalImporter() {
  const [, params] = useRoute('/portal/importer/:token');
  const token = params?.token || '';
  const { toast } = useToast();

  const [session, setSession] = useState<PortalSessionResponse | null>(null);
  const [uiStatus, setUiStatus] = useState<UiStatus>('loading');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // form state
  const [agreed, setAgreed] = useState(false);
  const [approverName, setApproverName] = useState('');
  const [approverEmail, setApproverEmail] = useState('');
  const [approverNote, setApproverNote] = useState('');
  const [rejecting, setRejecting] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const mapStatus = (status: string): UiStatus =>
    status === 'active' ? 'active' :
    status === 'approved' ? 'approved' :
    status === 'rejected' ? 'rejected' :
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
      const data = await getImporterSession(token);
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

  const handleApprove = async () => {
    if (!agreed || submitting) return;
    setSubmitting(true);
    try {
      const result = await approveImporter(token, {
        approver_name: approverName || undefined,
        approver_email: approverEmail || undefined,
        note: approverNote || undefined,
      });
      toast({
        title: 'Protocol approved',
        description: result.message || 'Your approval has been recorded.',
      });
      await loadSession();
    } catch (e) {
      if (e instanceof PortalApiError && e.status === 409) {
        toast({
          title: 'Already acted on',
          description: 'This portal link has already been used.',
        });
        await loadSession();
      } else {
        toast({
          title: 'Approval failed',
          description: e instanceof Error ? e.message : 'Unknown error',
          variant: 'destructive' as any,
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleReject = async () => {
    if (!rejectReason.trim() || submitting) return;
    setSubmitting(true);
    try {
      const result = await rejectImporter(token, {
        reason: rejectReason.trim(),
        reviewer_name: approverName || undefined,
        reviewer_email: approverEmail || undefined,
      });
      toast({
        title: 'Change request sent',
        description: result.message || 'Your ops contact has been notified.',
      });
      await loadSession();
    } catch (e) {
      if (e instanceof PortalApiError && e.status === 409) {
        toast({
          title: 'Already acted on',
          description: 'This portal link has already been used.',
        });
        await loadSession();
      } else {
        toast({
          title: 'Request failed',
          description: e instanceof Error ? e.message : 'Unknown error',
          variant: 'destructive' as any,
        });
      }
    } finally {
      setSubmitting(false);
    }
  };

  // ── Layout ────────────────────────────────────────────────────────────
  const header = (
    <header className="border-b bg-card h-14 flex items-center justify-between px-6 sticky top-0 z-10">
      <div className="flex items-center gap-3">
        <span className="font-mono font-bold text-primary text-lg tracking-tight">Labelforge</span>
        <span className="text-muted-foreground text-sm">· Importer Portal</span>
      </div>
      <div className="flex items-center gap-2">
        {token && <Badge variant="outline" className="text-xs">Token: {token.slice(0, 12)}…</Badge>}
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
          <p className="text-sm mt-3">Loading approval request…</p>
        </div>
      </div>
    );
  }

  if (uiStatus === 'invalid' || uiStatus === 'expired' || uiStatus === 'error') {
    const title =
      uiStatus === 'expired' ? 'Link expired' :
      uiStatus === 'invalid' ? 'Link not recognised' :
      'Something went wrong';
    const icon = uiStatus === 'error' ? AlertCircle : XCircle;
    const IconC = icon;
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
            Please contact your Nakoda Art & Craft representative to get a fresh link.
          </p>
        </div>
      </div>
    );
  }

  const order = session?.order;
  const importer = session?.importer;
  const items = session?.items || [];
  const importerName = importer?.name || 'Your brand';

  // Terminal states
  if (uiStatus === 'approved' || uiStatus === 'rejected') {
    const approved = uiStatus === 'approved';
    return (
      <div className="min-h-screen bg-background text-foreground">
        {header}
        <div className="max-w-3xl mx-auto py-10 px-6">
          <div className="text-center space-y-6 py-16">
            <div className="flex justify-center">
              <div className={`w-20 h-20 rounded-full flex items-center justify-center ${approved ? 'bg-green-100' : 'bg-red-100'}`}>
                {approved
                  ? <CheckCircle2 className="w-10 h-10 text-green-600" />
                  : <XCircle className="w-10 h-10 text-red-600" />}
              </div>
            </div>
            <div>
              <h2 className="text-2xl font-bold">
                {approved ? 'Protocol Approved' : 'Change Request Submitted'}
              </h2>
              <p className="text-muted-foreground text-sm mt-2 max-w-sm mx-auto">
                {approved
                  ? `Thank you! Your approval has been recorded. Nakoda Art & Craft will begin label generation for ${order?.po_number || 'this order'}.`
                  : 'Your request has been sent to Nakoda Art & Craft. They will follow up with revised artwork.'}
              </p>
            </div>
            <div className="border rounded-xl p-5 bg-card text-sm text-left space-y-2 max-w-sm mx-auto">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Order</span>
                <span className="font-medium font-mono">{order?.po_number || order?.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Importer</span>
                <span className="font-medium">{importerName}</span>
              </div>
              {session?.action_taken_at && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Action at</span>
                  <span className="font-medium">
                    {new Date(session.action_taken_at).toLocaleString()}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Active / awaiting action
  return (
    <div className="min-h-screen bg-background text-foreground">
      {header}

      <div className="max-w-3xl mx-auto py-10 px-6 space-y-8">
        {/* Hero */}
        <div className="border rounded-xl p-6 bg-card">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
              <Building2 className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold">{importerName}</h1>
              <p className="text-sm text-muted-foreground mt-1">
                <span className="font-medium text-foreground">Nakoda Art & Craft</span>
                {' '}has prepared labels for your review on{' '}
                <span className="font-mono text-foreground">{order?.po_number || order?.id}</span>.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-6 mt-5 text-sm">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Package className="w-3.5 h-3.5" />
              {items.length} item{items.length === 1 ? '' : 's'}
            </div>
            {importer?.code && (
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Tag className="w-3.5 h-3.5" /> {importer.code}
              </div>
            )}
            {session?.expires_at && (
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <Clock className="w-3.5 h-3.5" />
                Expires {new Date(session.expires_at).toLocaleDateString()}
              </div>
            )}
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <Shield className="w-3.5 h-3.5" /> Secure portal link
            </div>
          </div>
        </div>

        <Tabs defaultValue="items">
          <TabsList>
            <TabsTrigger value="items">Items ({items.length})</TabsTrigger>
            <TabsTrigger value="summary">Order Summary</TabsTrigger>
          </TabsList>

          <TabsContent value="items" className="mt-4 space-y-3">
            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-8">
                No items attached to this order yet.
              </p>
            ) : (
              items.map((it) => (
                <div key={it.id} className="flex items-center gap-3 p-4 border rounded-lg bg-card text-sm">
                  <Package className="w-4 h-4 text-muted-foreground shrink-0" />
                  <div className="flex-1">
                    <div className="font-mono text-xs text-muted-foreground">{it.item_no}</div>
                    <div className="font-medium mt-0.5">ID: {it.id}</div>
                  </div>
                  <Badge variant="outline" className="text-xs">{it.state}</Badge>
                </div>
              ))
            )}
          </TabsContent>

          <TabsContent value="summary" className="mt-4 space-y-3">
            <div className="border rounded-xl overflow-hidden">
              <div className="px-4 py-3 bg-muted/50 border-b text-sm font-semibold">Order Details</div>
              <div className="p-4 grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">PO Number</span>
                  <div className="font-medium mt-1 font-mono">{order?.po_number || '—'}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Order ID</span>
                  <div className="font-medium mt-1 font-mono text-xs">{order?.id}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Importer</span>
                  <div className="font-medium mt-1">{importerName}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">Item Count</span>
                  <div className="font-medium mt-1 font-mono">{order?.item_count ?? items.length}</div>
                </div>
              </div>
            </div>
          </TabsContent>
        </Tabs>

        {/* Action panel */}
        {!rejecting ? (
          <div className="border rounded-xl p-6 space-y-4 bg-card">
            <h3 className="font-semibold">Your Approval</h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-muted-foreground">Your name (optional)</label>
                <input
                  type="text"
                  className="w-full mt-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={approverName}
                  onChange={(e) => setApproverName(e.target.value)}
                  placeholder="Jane Importer"
                />
              </div>
              <div>
                <label className="text-xs text-muted-foreground">Email (optional)</label>
                <input
                  type="email"
                  className="w-full mt-1 rounded-lg border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  value={approverEmail}
                  onChange={(e) => setApproverEmail(e.target.value)}
                  placeholder="jane@example.com"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-muted-foreground">Note (optional)</label>
              <textarea
                className="w-full mt-1 h-20 rounded-lg border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
                value={approverNote}
                onChange={(e) => setApproverNote(e.target.value)}
                placeholder="Any comments for the ops team…"
              />
            </div>

            <label className="flex items-start gap-3 cursor-pointer">
              <Checkbox checked={agreed} onCheckedChange={(v) => setAgreed(!!v)} className="mt-0.5" />
              <p className="text-sm text-muted-foreground leading-relaxed">
                I confirm that I have reviewed the labeling protocol above and that it accurately reflects
                our requirements. I authorise{' '}
                <strong className="text-foreground">Nakoda Art & Craft</strong> to proceed with label
                production for our orders based on this specification.
              </p>
            </label>
            <div className="flex gap-3">
              <Button
                onClick={handleApprove}
                disabled={!agreed || submitting}
                className="flex-1"
              >
                {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <ThumbsUp className="w-4 h-4 mr-2" />}
                Approve Protocol
              </Button>
              <Button
                variant="outline"
                onClick={() => setRejecting(true)}
                disabled={submitting}
                className="text-destructive border-destructive/30 hover:bg-destructive/5"
              >
                <ThumbsDown className="w-4 h-4 mr-2" /> Request Changes
              </Button>
            </div>
          </div>
        ) : (
          <div className="border border-destructive/30 rounded-xl p-6 space-y-4 bg-card">
            <h3 className="font-semibold text-destructive">Request Changes</h3>
            <textarea
              className="w-full h-32 rounded-lg border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary"
              placeholder="Describe what needs to be changed…"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
            />
            <div className="flex gap-3">
              <Button
                variant="destructive"
                disabled={!rejectReason.trim() || submitting}
                onClick={handleReject}
              >
                {submitting ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                Submit Change Request
              </Button>
              <Button
                variant="ghost"
                onClick={() => { setRejecting(false); setRejectReason(''); }}
                disabled={submitting}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
