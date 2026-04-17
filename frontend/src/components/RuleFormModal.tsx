/**
 * Create / edit a compliance rule.
 *
 * Opens as a modal dialog. The `logic` field is a JSON object with shape
 * `{"conditions": <AST>, "requirements": <AST>, "category"?: str}` and is
 * validated locally before POST/PUT. Active (promoted) rules are immutable
 * on the server, so the form refuses to render edit mode for them.
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { DslEditor } from './DslEditor';
import {
  ComplianceRule,
  RuleCreatePayload,
  RuleLogic,
  RuleUpdatePayload,
  useCreateRuleMutation,
  useUpdateRuleMutation,
} from '@/hooks/useRules';

interface RuleFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** When set, the form opens in edit mode for this rule. */
  rule?: ComplianceRule | null;
  onSaved?: (rule: ComplianceRule) => void;
}

const DEFAULT_LOGIC = `{
  "category": "compliance",
  "conditions": {
    "op": "==",
    "field": "destination",
    "value": "US"
  },
  "requirements": {
    "op": "true"
  }
}`;

const REGIONS = ['US', 'US-CA', 'EU', 'UK', 'CA', 'AU', 'JP'];
const PLACEMENTS = ['both', 'carton', 'product', 'hangtag'];

export function RuleFormModal({ open, onOpenChange, rule, onSaved }: RuleFormModalProps) {
  const { toast } = useToast();
  const isEdit = !!rule;

  const [code, setCode] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [region, setRegion] = useState('US');
  const [placement, setPlacement] = useState('both');
  const [logicText, setLogicText] = useState(DEFAULT_LOGIC);

  // Reset form state whenever the modal opens or the target rule changes.
  useEffect(() => {
    if (!open) return;
    if (rule) {
      setCode(rule.code);
      setTitle(rule.title);
      setDescription(rule.description ?? '');
      setRegion(rule.region);
      setPlacement(rule.placement);
      setLogicText(rule.logic ? JSON.stringify(rule.logic, null, 2) : DEFAULT_LOGIC);
    } else {
      setCode('');
      setTitle('');
      setDescription('');
      setRegion('US');
      setPlacement('both');
      setLogicText(DEFAULT_LOGIC);
    }
  }, [open, rule]);

  const logicValidation = useMemo<{ parsed: RuleLogic | null; error: string | null }>(() => {
    const trimmed = logicText.trim();
    if (!trimmed) return { parsed: null, error: null };
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        return { parsed: null, error: 'Logic must be a JSON object' };
      }
      return { parsed: parsed as RuleLogic, error: null };
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Invalid JSON';
      return { parsed: null, error: msg };
    }
  }, [logicText]);

  const createMutation = useCreateRuleMutation();
  const updateMutation = useUpdateRuleMutation(rule?.id ?? '');

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const canSave = code.trim() && title.trim() && !logicValidation.error;

  const handleSave = async () => {
    if (!canSave) return;
    try {
      if (isEdit && rule) {
        const body: RuleUpdatePayload = {
          title: title.trim(),
          description: description,
          region,
          placement,
          logic: logicValidation.parsed,
        };
        const updated = await updateMutation.mutateAsync(body);
        toast({ title: 'Rule updated', description: `${updated.code} v${updated.version}` });
        onSaved?.(updated);
      } else {
        const body: RuleCreatePayload = {
          code: code.trim(),
          title: title.trim(),
          description,
          region,
          placement,
          logic: logicValidation.parsed,
        };
        const created = await createMutation.mutateAsync(body);
        toast({
          title: 'Rule staged',
          description: `${created.code} v${created.version} — promote to activate`,
        });
        onSaved?.(created);
      }
      onOpenChange(false);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Save failed';
      toast({ title: 'Save failed', description: msg, variant: 'destructive' });
    }
  };

  const promotedBlocked = isEdit && rule?.active;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit rule ${rule?.code} v${rule?.version}` : 'Propose a new rule'}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? 'Changes stay in staging until the rule is promoted.'
              : 'New rules are created in staging. Promote to activate them across the tenant.'}
          </DialogDescription>
        </DialogHeader>

        {promotedBlocked && (
          <div className="rounded-md border border-yellow-300 bg-yellow-50 p-3 text-xs text-yellow-800">
            This rule is already promoted. Active rules are immutable — create a new version
            with "Propose new rule" (same code) and promote it instead.
          </div>
        )}

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="rule-code" className="text-xs">Rule code</Label>
              <Input
                id="rule-code"
                placeholder="CA65-WARNING"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                disabled={isEdit}
                className="font-mono"
              />
              {isEdit && <p className="text-[11px] text-muted-foreground">Codes are immutable once created.</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="rule-title" className="text-xs">Title</Label>
              <Input
                id="rule-title"
                placeholder="California Prop 65 warning required"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={promotedBlocked}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="rule-desc" className="text-xs">Description</Label>
            <Textarea
              id="rule-desc"
              placeholder="What this rule enforces, why it matters, and any known edge cases."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={promotedBlocked}
              rows={3}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label className="text-xs">Region</Label>
              <Select value={region} onValueChange={setRegion} disabled={promotedBlocked}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {REGIONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Placement</Label>
              <Select value={placement} onValueChange={setPlacement} disabled={promotedBlocked}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  {PLACEMENTS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Logic (DSL)</Label>
              <span className="text-[11px] text-muted-foreground font-mono">
                {'{"conditions": <AST>, "requirements": <AST>}'}
              </span>
            </div>
            <DslEditor
              value={logicText}
              onChange={setLogicText}
              error={logicValidation.error}
              readOnly={promotedBlocked}
              rows={14}
              ariaLabel="Rule logic DSL"
            />
            <p className="text-[11px] text-muted-foreground">
              Operators: <span className="font-mono">== != &gt; &lt; &gt;= &lt;= in not_in AND OR NOT</span>.
              Use <span className="font-mono">{'{"op": "true"}'}</span> as the always-match
              requirement when the rule is purely a warning.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={!canSave || isSaving || promotedBlocked}>
            {isSaving ? 'Saving…' : isEdit ? 'Save changes' : 'Create in staging'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
