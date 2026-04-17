/**
 * Rule detail panel. Opens as a side sheet with three tabs:
 *   1. "Overview"  — metadata + DSL preview + promote / rollback actions.
 *   2. "Dry run"   — test a proposed change against sampled order items.
 *   3. "History"   — audit trail (create, update, promote, rollback).
 *
 * Surfaces the version chain (superseded versions of the same rule code)
 * so compliance reviewers can walk the lineage without running SQL.
 */
import React, { useMemo, useState } from 'react';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  CheckCircle2, Clock, AlertTriangle, Rocket, Undo2, Pencil,
  TrendingUp, TrendingDown, Minus, History,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { DslPreview } from './DslEditor';
import {
  ComplianceRule,
  useRules,
  useRuleAuditLog,
  useDryRunRuleMutation,
  usePromoteRuleMutation,
  useRollbackRuleMutation,
  DryRunResponse,
} from '@/hooks/useRules';

interface RuleDetailSheetProps {
  ruleId: string | null;
  rule: ComplianceRule | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit?: (rule: ComplianceRule) => void;
}

const STATUS_META: Record<string, { color: string; icon: React.ReactNode; label: string }> = {
  active:   { color: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: <CheckCircle2 className="w-3 h-3" />, label: 'Active' },
  staged:   { color: 'bg-yellow-50 text-yellow-700 border-yellow-200',    icon: <Clock className="w-3 h-3" />,        label: 'Staged' },
  inactive: { color: 'bg-gray-100 text-gray-500 border-gray-200',          icon: <AlertTriangle className="w-3 h-3" />, label: 'Inactive' },
};

function statusOf(rule: ComplianceRule): keyof typeof STATUS_META {
  if (rule.active) return 'active';
  return 'staged';
}

export function RuleDetailSheet({ ruleId, rule, open, onOpenChange, onEdit }: RuleDetailSheetProps) {
  if (!ruleId || !rule) return null;
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[640px] sm:max-w-[640px] overflow-y-auto">
        <SheetHeader className="space-y-1.5">
          <SheetTitle className="flex items-center gap-2">
            <span className="font-mono text-base">{rule.code}</span>
            <Badge variant="outline" className="text-xs">v{rule.version}</Badge>
            <StatusBadge rule={rule} />
          </SheetTitle>
          <SheetDescription>{rule.title}</SheetDescription>
        </SheetHeader>

        <Tabs defaultValue="overview" className="mt-4">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="dry-run">Dry run</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-4 space-y-4">
            <OverviewPane rule={rule} onEdit={onEdit} />
          </TabsContent>

          <TabsContent value="dry-run" className="mt-4 space-y-4">
            <DryRunPane rule={rule} />
          </TabsContent>

          <TabsContent value="history" className="mt-4 space-y-4">
            <HistoryPane rule={rule} />
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}

function StatusBadge({ rule }: { rule: ComplianceRule }) {
  const meta = STATUS_META[statusOf(rule)];
  return (
    <Badge variant="outline" className={`text-xs gap-1 ${meta.color}`}>
      {meta.icon}
      {meta.label}
    </Badge>
  );
}

/* ── Overview tab ───────────────────────────────────────────────────────── */

function OverviewPane({ rule, onEdit }: { rule: ComplianceRule; onEdit?: (r: ComplianceRule) => void }) {
  const { toast } = useToast();
  const promote = usePromoteRuleMutation();
  const rollback = useRollbackRuleMutation();

  // Sibling versions of the same rule_code form the supersedes chain.
  const supersedes = useRules({ code: rule.code, limit: 50 });
  const chain = useMemo(() => {
    const all = supersedes.data?.rules ?? [];
    return [...all].sort((a, b) => b.version - a.version);
  }, [supersedes.data]);

  const logicText = useMemo(
    () => (rule.logic ? JSON.stringify(rule.logic, null, 2) : '{}'),
    [rule.logic],
  );

  const handlePromote = async () => {
    try {
      await promote.mutateAsync(rule.id);
      toast({ title: 'Rule promoted', description: `${rule.code} v${rule.version} is now active` });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Promote failed';
      toast({ title: 'Promote failed', description: msg, variant: 'destructive' });
    }
  };

  const handleRollback = async () => {
    try {
      const res = await rollback.mutateAsync(rule.id);
      toast({ title: 'Rule rolled back', description: res.message });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Rollback failed';
      toast({ title: 'Rollback failed', description: msg, variant: 'destructive' });
    }
  };

  const metadata: Array<[string, React.ReactNode]> = [
    ['Region', <span className="font-mono text-xs">{rule.region}</span>],
    ['Placement', <span className="font-mono text-xs">{rule.placement}</span>],
    ['Updated', <span className="tabular-nums text-xs">{new Date(rule.updated_at).toLocaleString()}</span>],
  ];

  return (
    <div className="space-y-4">
      {rule.description && (
        <p className="text-sm text-muted-foreground leading-relaxed">{rule.description}</p>
      )}

      <div className="grid grid-cols-3 gap-3">
        {metadata.map(([label, value]) => (
          <div key={label} className="rounded-md border bg-card p-3">
            <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</p>
            <div className="mt-1">{value}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {!rule.active && (
          <Button size="sm" onClick={handlePromote} disabled={promote.isPending}>
            <Rocket className="w-3.5 h-3.5 mr-1.5" />
            {promote.isPending ? 'Promoting…' : 'Promote to active'}
          </Button>
        )}
        {rule.active && (
          <Button size="sm" variant="destructive" onClick={handleRollback} disabled={rollback.isPending}>
            <Undo2 className="w-3.5 h-3.5 mr-1.5" />
            {rollback.isPending ? 'Rolling back…' : 'Roll back to previous'}
          </Button>
        )}
        {!rule.active && onEdit && (
          <Button size="sm" variant="outline" onClick={() => onEdit(rule)}>
            <Pencil className="w-3.5 h-3.5 mr-1.5" />
            Edit staged rule
          </Button>
        )}
      </div>

      <Separator />

      <div>
        <div className="flex items-center justify-between mb-2">
          <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Logic DSL
          </Label>
        </div>
        <DslPreview value={logicText} />
      </div>

      <Separator />

      <div>
        <Label className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Version chain
        </Label>
        {supersedes.isLoading ? (
          <p className="text-xs text-muted-foreground mt-2">Loading chain…</p>
        ) : chain.length === 0 ? (
          <p className="text-xs text-muted-foreground mt-2">No other versions.</p>
        ) : (
          <ol className="mt-2 space-y-1.5">
            {chain.map((v) => (
              <li
                key={v.id}
                className={`flex items-center gap-2 rounded border p-2 text-xs ${
                  v.id === rule.id ? 'border-primary bg-primary/5' : 'bg-card'
                }`}
              >
                <Badge variant="outline" className="text-[10px]">v{v.version}</Badge>
                <StatusBadge rule={v} />
                <span className="flex-1 truncate text-muted-foreground">{v.title}</span>
                <span className="tabular-nums text-[11px] text-muted-foreground">
                  {new Date(v.updated_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

/* ── Dry-run tab ────────────────────────────────────────────────────────── */

const DEFAULT_SAMPLE = `[
  {
    "item_no": "SKU-A",
    "destination": "US",
    "material": "cotton",
    "weight": 0.5
  },
  {
    "item_no": "SKU-B",
    "destination": "EU",
    "material": "polyester",
    "weight": 1.2
  }
]`;

function DryRunPane({ rule }: { rule: ComplianceRule }) {
  const { toast } = useToast();
  const [sampleText, setSampleText] = useState<string>(DEFAULT_SAMPLE);
  const [orderId, setOrderId] = useState('');
  const [itemIds, setItemIds] = useState('');
  const [result, setResult] = useState<DryRunResponse | null>(null);
  const dryRun = useDryRunRuleMutation();

  const handleRun = async () => {
    try {
      const payload: Parameters<typeof dryRun.mutateAsync>[0] = {
        proposed: {
          code: rule.code,
          title: rule.title,
          description: rule.description,
          region: rule.region,
          placement: rule.placement,
          logic: rule.logic ?? undefined,
        },
      };
      const trimmed = sampleText.trim();
      if (trimmed) {
        const parsed = JSON.parse(trimmed);
        if (!Array.isArray(parsed)) throw new Error('Sample contexts must be a JSON array');
        payload.sample_contexts = parsed;
      } else if (itemIds.trim()) {
        payload.item_ids = itemIds.split(',').map((s) => s.trim()).filter(Boolean);
      } else if (orderId.trim()) {
        payload.order_id = orderId.trim();
      }
      const res = await dryRun.mutateAsync(payload);
      setResult(res);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Dry run failed';
      toast({ title: 'Dry run failed', description: msg, variant: 'destructive' });
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Evaluate this rule against scoped items without promoting it. Provide
        inline sample contexts (highest priority), explicit item IDs, or an
        order ID — scopes apply in that order.
      </p>

      <div className="space-y-1.5">
        <Label className="text-xs">Sample contexts (JSON array)</Label>
        <Textarea
          rows={8}
          className="font-mono text-xs"
          value={sampleText}
          onChange={(e) => setSampleText(e.target.value)}
          placeholder='[{"item_no": "SKU-A", "destination": "US"}]'
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <Label className="text-xs">or Order ID</Label>
          <input
            className="h-9 w-full rounded-md border bg-background px-3 font-mono text-xs"
            placeholder="ord-..."
            value={orderId}
            onChange={(e) => setOrderId(e.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">or Item IDs (comma-separated)</Label>
          <input
            className="h-9 w-full rounded-md border bg-background px-3 font-mono text-xs"
            placeholder="item-1, item-2"
            value={itemIds}
            onChange={(e) => setItemIds(e.target.value)}
          />
        </div>
      </div>

      <Button onClick={handleRun} disabled={dryRun.isPending}>
        {dryRun.isPending ? 'Evaluating…' : 'Run dry-run'}
      </Button>

      {result && <DryRunResult result={result} />}
    </div>
  );
}

function DryRunResult({ result }: { result: DryRunResponse }) {
  return (
    <div className="space-y-3 rounded-lg border bg-card p-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Dry run result</p>
        <Badge variant="outline" className="text-xs">
          {result.items_evaluated} item{result.items_evaluated === 1 ? '' : 's'} evaluated
        </Badge>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <BucketCard
          label="Newly failing"
          count={result.newly_failing.length}
          color="text-red-600"
          icon={<TrendingDown className="w-4 h-4" />}
          items={result.newly_failing}
        />
        <BucketCard
          label="Newly passing"
          count={result.newly_passing.length}
          color="text-emerald-600"
          icon={<TrendingUp className="w-4 h-4" />}
          items={result.newly_passing}
        />
        <BucketCard
          label="Unchanged"
          count={result.unchanged.length}
          color="text-muted-foreground"
          icon={<Minus className="w-4 h-4" />}
          items={result.unchanged}
        />
      </div>
    </div>
  );
}

function BucketCard({
  label, count, color, icon, items,
}: {
  label: string;
  count: number;
  color: string;
  icon: React.ReactNode;
  items: string[];
}) {
  return (
    <div className="rounded-md border bg-background p-3">
      <div className={`flex items-center justify-center gap-1.5 ${color}`}>
        {icon}
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className={`mt-1 text-xl font-mono font-semibold tabular-nums ${color}`}>{count}</p>
      {items.length > 0 && (
        <p className="mt-1 truncate text-[10px] text-muted-foreground font-mono" title={items.join(', ')}>
          {items.slice(0, 3).join(', ')}{items.length > 3 ? `, +${items.length - 3}` : ''}
        </p>
      )}
    </div>
  );
}

/* ── History tab ────────────────────────────────────────────────────────── */

function HistoryPane({ rule }: { rule: ComplianceRule }) {
  const audit = useRuleAuditLog(rule.id, { limit: 50 });
  const entries = audit.data?.entries ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <History className="w-3.5 h-3.5" />
        Audit trail for {rule.code} v{rule.version}
      </div>

      {audit.isLoading && <p className="text-xs text-muted-foreground">Loading audit log…</p>}
      {audit.isError && <p className="text-xs text-destructive">Failed to load audit log.</p>}
      {!audit.isLoading && entries.length === 0 && (
        <p className="text-xs text-muted-foreground">No audit entries yet.</p>
      )}

      <ol className="space-y-2">
        {entries.map((e) => (
          <li key={e.id} className="rounded-md border bg-card p-3">
            <div className="flex items-center justify-between">
              <Badge variant="outline" className={auditBadgeColor(e.action)}>
                {e.action}
              </Badge>
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {new Date(e.created_at).toLocaleString()}
              </span>
            </div>
            {e.detail && <p className="mt-1.5 text-xs text-muted-foreground">{e.detail}</p>}
            <p className="mt-1 text-[11px] text-muted-foreground">
              by <span className="font-mono">{e.actor ?? 'system'}</span>
              <span className="mx-1">·</span>
              {e.actor_type}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function auditBadgeColor(action: string): string {
  switch (action) {
    case 'create':   return 'text-xs bg-blue-50 text-blue-700 border-blue-200';
    case 'update':   return 'text-xs bg-indigo-50 text-indigo-700 border-indigo-200';
    case 'promote':  return 'text-xs bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'rollback': return 'text-xs bg-orange-50 text-orange-700 border-orange-200';
    default:         return 'text-xs';
  }
}
