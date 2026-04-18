import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  MessageSquare, Send, CheckCircle2, Clock,
  Bot, User, Loader2, AlertTriangle, ShieldAlert, Wifi, WifiOff,
} from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  useThreads,
  useThreadMessages,
  useAddMessage,
  useSelectOption,
  useResolveThread,
  useEscalateThread,
  useThreadLive,
} from '@/hooks/useHitl';
import type { HitlMessage, HitlThread, ThreadStatus, Priority } from '@/api/hitl';

// ── Priority + status helpers ──────────────────────────────────────────────

const PRIORITY_STYLE: Record<Priority, string> = {
  P0: 'bg-red-50 text-red-600 border-red-200',
  P1: 'bg-yellow-50 text-yellow-600 border-yellow-200',
  P2: 'bg-gray-50 text-gray-500 border-gray-200',
};

const PRIORITY_RANK: Record<Priority, number> = { P0: 0, P1: 1, P2: 2 };

function statusDot(status: ThreadStatus) {
  switch (status) {
    case 'OPEN':
      return <div className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />;
    case 'IN_PROGRESS':
      return <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />;
    case 'ESCALATED':
      return <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />;
    case 'RESOLVED':
      return <div className="w-2 h-2 rounded-full bg-emerald-500" />;
    default:
      return <div className="w-2 h-2 rounded-full bg-gray-400" />;
  }
}

function statusBadge(status: ThreadStatus) {
  const cls = {
    OPEN: 'bg-orange-50 text-orange-700 border-orange-200',
    IN_PROGRESS: 'bg-blue-50 text-blue-700 border-blue-200',
    ESCALATED: 'bg-red-50 text-red-700 border-red-200',
    RESOLVED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  }[status];
  const label = status.replace('_', ' ').toLowerCase();
  return (
    <Badge variant="outline" className={`text-xs ${cls}`}>
      {status === 'RESOLVED' && <CheckCircle2 className="w-3 h-3 mr-1" />}
      {status === 'OPEN' && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
      {status === 'IN_PROGRESS' && <Loader2 className="w-3 h-3 mr-1 animate-spin" />}
      {status === 'ESCALATED' && <ShieldAlert className="w-3 h-3 mr-1" />}
      {label}
    </Badge>
  );
}

function slaLabel(thread: HitlThread): { text: string; tone: 'ok' | 'warn' | 'breach' } {
  if (!thread.sla_deadline) return { text: 'No SLA', tone: 'ok' };
  const diffMs = new Date(thread.sla_deadline).getTime() - Date.now();
  if (diffMs < 0) return { text: `SLA breached ${fmtDuration(-diffMs)} ago`, tone: 'breach' };
  const tone = diffMs < 30 * 60 * 1000 ? 'warn' : 'ok';
  return { text: `SLA in ${fmtDuration(diffMs)}`, tone };
}

function fmtDuration(ms: number): string {
  const mins = Math.round(ms / 60_000);
  if (mins < 60) return `${mins}m`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

// ── Message bubble ─────────────────────────────────────────────────────────

function ThreadBubble({
  msg,
  onPickOption,
  optionPending,
  canInteract,
}: {
  msg: HitlMessage;
  onPickOption?: (option: string) => void;
  optionPending?: boolean;
  canInteract: boolean;
}) {
  if (msg.role === 'system') {
    return (
      <div className="flex justify-center py-2">
        <div className="bg-muted text-muted-foreground text-[11px] px-3 py-1.5 rounded-full max-w-md text-center">
          {msg.content}
        </div>
      </div>
    );
  }

  const isAgent = msg.role === 'agent';
  const ctxOptions = Array.isArray(msg.context?.options)
    ? (msg.context!.options as unknown[]).filter((o): o is string => typeof o === 'string')
    : [];
  const selectedOption =
    typeof msg.context?.selected_option === 'string' ? (msg.context!.selected_option as string) : null;

  return (
    <div className={`flex gap-2.5 ${isAgent ? '' : 'flex-row-reverse'}`}>
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-bold
          ${isAgent ? 'bg-primary/10 text-primary' : 'bg-orange-100 text-orange-700'}`}
      >
        {isAgent ? <Bot className="w-3.5 h-3.5" /> : <User className="w-3.5 h-3.5" />}
      </div>
      <div className={`max-w-[75%] space-y-1.5 ${isAgent ? '' : 'items-end flex flex-col'}`}>
        <div
          className={`px-3.5 py-2.5 rounded-xl text-sm leading-relaxed whitespace-pre-wrap
            ${isAgent ? 'bg-card border shadow-sm rounded-tl-sm' : 'bg-primary text-primary-foreground rounded-tr-sm'}`}
        >
          {msg.content}
        </div>
        {ctxOptions.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {ctxOptions.map((opt) => {
              const isSelected = selectedOption === opt;
              return (
                <Button
                  key={opt}
                  variant={isSelected ? 'default' : 'outline'}
                  size="sm"
                  className="text-xs h-7 rounded-full"
                  disabled={!canInteract || !!selectedOption || optionPending}
                  onClick={() => onPickOption?.(opt)}
                >
                  {opt}
                  {isSelected && <CheckCircle2 className="w-3 h-3 ml-1" />}
                </Button>
              );
            })}
          </div>
        )}
        <div className="text-[10px] text-muted-foreground px-1">
          {new Date(msg.created_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}

// ── Agent-typing indicator ─────────────────────────────────────────────────
//
// Mirrors the ThreadBubble agent-side layout so the "thinking" bubble
// slots naturally into the message stream. We render three CSS-animated
// dots rather than a spinner so the cue reads as "composing a reply" (a
// human-style hint) rather than "loading a page".

function AgentTypingBubble({ agentId }: { agentId: string }) {
  return (
    <div className="flex gap-2.5" role="status" aria-live="polite">
      <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 bg-primary/10 text-primary">
        <Bot className="w-3.5 h-3.5" />
      </div>
      <div className="max-w-[75%] space-y-1.5">
        <div className="px-3.5 py-2.5 rounded-xl rounded-tl-sm bg-card border shadow-sm">
          <span className="flex items-center gap-1 h-4" aria-label={`${agentId} is typing`}>
            <span
              className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce"
              style={{ animationDelay: '0ms' }}
            />
            <span
              className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce"
              style={{ animationDelay: '150ms' }}
            />
            <span
              className="w-1.5 h-1.5 rounded-full bg-muted-foreground/70 animate-bounce"
              style={{ animationDelay: '300ms' }}
            />
          </span>
        </div>
        <div className="text-[10px] text-muted-foreground px-1">
          {agentId} is thinking…
        </div>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────

export default function Hitl() {
  const { toast } = useToast();
  const { data: listData, isLoading: listLoading } = useThreads({ limit: 100 });
  const threads = listData?.threads ?? [];

  // Selection: first non-resolved, else first thread, else null.
  const [selectedId, setSelectedId] = useState<string | null>(null);
  useEffect(() => {
    if (selectedId && threads.some((t) => t.id === selectedId)) return;
    const firstOpen = threads.find((t) => t.status !== 'RESOLVED');
    setSelectedId(firstOpen?.id ?? threads[0]?.id ?? null);
  }, [threads, selectedId]);

  const selected = threads.find((t) => t.id === selectedId) ?? null;

  // Sort: active priority first, then P0 → P2, then oldest first.
  const sortedThreads = useMemo(() => {
    const isTerminal = (s: ThreadStatus) => s === 'RESOLVED';
    return [...threads].sort((a, b) => {
      const ta = isTerminal(a.status) ? 1 : 0;
      const tb = isTerminal(b.status) ? 1 : 0;
      if (ta !== tb) return ta - tb;
      const pa = PRIORITY_RANK[a.priority] ?? 99;
      const pb = PRIORITY_RANK[b.priority] ?? 99;
      if (pa !== pb) return pa - pb;
      return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });
  }, [threads]);

  const openCount = threads.filter((t) => t.status === 'OPEN').length;
  const inProgCount = threads.filter((t) => t.status === 'IN_PROGRESS').length;
  const escalatedCount = threads.filter((t) => t.status === 'ESCALATED').length;
  const resolvedCount = threads.filter((t) => t.status === 'RESOLVED').length;

  return (
    <div className="flex h-[calc(100vh-56px)]">
      {/* ── Sidebar ───────────────────────────────────────────────────── */}
      <div className="w-80 border-r bg-card flex flex-col shrink-0">
        <div className="p-4 border-b shrink-0">
          <h2 className="text-lg font-bold tracking-tight">HiTL Inbox</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {openCount} open · {inProgCount} in-progress · {escalatedCount} escalated · {resolvedCount} resolved
          </p>
        </div>

        <div className="p-3 border-b shrink-0">
          <div className="grid grid-cols-4 gap-2">
            <StatCard tone="orange" value={openCount} label="Open" />
            <StatCard tone="blue" value={inProgCount} label="Active" />
            <StatCard tone="red" value={escalatedCount} label="Escalated" />
            <StatCard tone="emerald" value={resolvedCount} label="Done" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {listLoading && (
            <div className="p-3 space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          )}

          {!listLoading && sortedThreads.length === 0 && (
            <div className="p-6 text-center text-xs text-muted-foreground">
              No HiTL threads. Agents will raise tickets here when they need human input.
            </div>
          )}

          {!listLoading &&
            sortedThreads.map((thread) => {
              const isSelected = selected?.id === thread.id;
              const sla = slaLabel(thread);
              return (
                <div
                  key={thread.id}
                  className={`p-3 border-b cursor-pointer transition-colors
                    ${isSelected ? 'bg-primary/5 border-l-2 border-l-primary' : 'hover:bg-muted/50 border-l-2 border-l-transparent'}`}
                  onClick={() => setSelectedId(thread.id)}
                >
                  <div className="flex items-start justify-between mb-1">
                    <div className="flex items-center gap-1.5 min-w-0">
                      {statusDot(thread.status)}
                      {thread.order_id && (
                        <span className="font-mono text-xs font-medium text-primary truncate">
                          {thread.order_id}
                        </span>
                      )}
                    </div>
                    <Badge variant="outline" className={`text-[10px] px-1.5 py-0 ${PRIORITY_STYLE[thread.priority]}`}>
                      {thread.priority}
                    </Badge>
                  </div>
                  <div className="text-sm font-medium truncate">
                    {thread.summary || '(no summary)'}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-0.5 flex items-center gap-1">
                    {thread.item_no && <span>Item {thread.item_no}</span>}
                    {thread.item_no && thread.agent_id && <span>·</span>}
                    {thread.agent_id && <span className="truncate">{thread.agent_id}</span>}
                  </div>
                  <div className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" />
                    <span className={
                      sla.tone === 'breach' ? 'text-red-600 font-medium' :
                      sla.tone === 'warn' ? 'text-orange-600' :
                      ''
                    }>
                      {sla.text}
                    </span>
                    <span className="ml-auto">{thread.message_count} msg</span>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* ── Main thread view ──────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col bg-background min-w-0">
        {selected ? (
          <ThreadDetail
            thread={selected}
            onSendResult={(kind) => {
              if (kind === 'sent') toast({ title: 'Message sent', description: 'Agent will pick up your response.' });
              if (kind === 'resolved') toast({ title: 'Thread resolved' });
              if (kind === 'escalated') toast({ title: 'Thread escalated' });
            }}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <MessageSquare className="w-12 h-12 text-muted-foreground/30 mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                {listLoading ? 'Loading threads…' : 'No thread selected.'}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Subcomponents ──────────────────────────────────────────────────────────

function StatCard({ tone, value, label }: { tone: 'orange' | 'blue' | 'red' | 'emerald'; value: number; label: string }) {
  const styles = {
    orange: 'bg-orange-50 border-orange-200 text-orange-700',
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    red: 'bg-red-50 border-red-200 text-red-700',
    emerald: 'bg-emerald-50 border-emerald-200 text-emerald-700',
  }[tone];
  return (
    <div className={`text-center p-2 rounded border ${styles}`}>
      <div className="text-lg font-bold leading-none">{value}</div>
      <div className="text-[10px] font-medium mt-0.5">{label}</div>
    </div>
  );
}

function ThreadDetail({
  thread,
  onSendResult,
}: {
  thread: HitlThread;
  onSendResult: (kind: 'sent' | 'resolved' | 'escalated') => void;
}) {
  const { toast } = useToast();
  const { data: messagesData, isLoading: messagesLoading } = useThreadMessages(thread.id);
  const addMessage = useAddMessage(thread.id);
  const selectOption = useSelectOption(thread.id);
  const resolveThread = useResolveThread(thread.id);
  const escalateThread = useEscalateThread(thread.id);
  const { connected, error: liveError, sendTyping, agentTyping } = useThreadLive(thread.id);

  const [draft, setDraft] = useState('');
  const chatEndRef = useRef<HTMLDivElement>(null);

  const messages = messagesData?.messages ?? [];
  const canInteract = thread.status !== 'RESOLVED';
  const sla = slaLabel(thread);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, thread.id]);

  const handleSend = async () => {
    const content = draft.trim();
    if (!content) return;
    try {
      await addMessage.mutateAsync({ content, role: 'human' });
      setDraft('');
      onSendResult('sent');
    } catch (err) {
      toast({
        title: 'Send failed',
        description: err instanceof Error ? err.message : 'Could not send message.',
        variant: 'destructive',
      });
    }
  };

  const handleResolve = async () => {
    const note = window.prompt('Optional resolution note:');
    if (note === null) return;
    try {
      await resolveThread.mutateAsync({ resolution_note: note || undefined });
      onSendResult('resolved');
    } catch (err) {
      toast({
        title: 'Resolve failed',
        description: err instanceof Error ? err.message : 'Could not resolve thread.',
        variant: 'destructive',
      });
    }
  };

  const handleEscalate = async () => {
    const reason = window.prompt('Escalation reason:');
    if (!reason) return;
    try {
      await escalateThread.mutateAsync({ reason });
      onSendResult('escalated');
    } catch (err) {
      toast({
        title: 'Escalate failed',
        description: err instanceof Error ? err.message : 'Could not escalate thread.',
        variant: 'destructive',
      });
    }
  };

  const handlePickOption = async (option: string) => {
    try {
      await selectOption.mutateAsync({ option });
    } catch (err) {
      toast({
        title: 'Selection failed',
        description: err instanceof Error ? err.message : 'Could not record option.',
        variant: 'destructive',
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    } else {
      sendTyping();
    }
  };

  return (
    <>
      <div className="p-4 border-b bg-card shrink-0">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="font-medium text-sm truncate">{thread.summary || '(no summary)'}</h3>
              {statusBadge(thread.status)}
              <Badge variant="outline" className={`text-xs ${PRIORITY_STYLE[thread.priority]}`}>
                {thread.priority}
              </Badge>
              <span
                className={`flex items-center gap-1 text-[11px] ${
                  connected ? 'text-emerald-600' : 'text-muted-foreground'
                }`}
                title={liveError ?? (connected ? 'Live connection open' : 'Live connection closed')}
              >
                {connected ? <Wifi className="w-3 h-3" /> : <WifiOff className="w-3 h-3" />}
                {connected ? 'live' : 'offline'}
              </span>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5 truncate">
              {thread.order_id && <>Order <span className="font-mono">{thread.order_id}</span></>}
              {thread.order_id && thread.item_no && ' · '}
              {thread.item_no && <>Item {thread.item_no}</>}
              {thread.agent_id && ` · Agent: ${thread.agent_id}`}
              {thread.blocking && (
                <> · <span className="text-orange-600">Blocking: {thread.blocking}</span></>
              )}
            </p>
            <p className="text-[11px] mt-0.5">
              <span
                className={
                  sla.tone === 'breach' ? 'text-red-600 font-medium' :
                  sla.tone === 'warn' ? 'text-orange-600' :
                  'text-muted-foreground'
                }
              >
                {sla.tone === 'breach' && <AlertTriangle className="w-3 h-3 inline mr-1" />}
                {sla.text}
              </span>
            </p>
          </div>
          {canInteract && (
            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant="outline"
                size="sm"
                onClick={handleEscalate}
                disabled={escalateThread.isPending || thread.status === 'ESCALATED'}
              >
                <ShieldAlert className="w-3.5 h-3.5 mr-1" />
                Escalate
              </Button>
              <Button
                variant="default"
                size="sm"
                onClick={handleResolve}
                disabled={resolveThread.isPending}
              >
                <CheckCircle2 className="w-3.5 h-3.5 mr-1" />
                Resolve
              </Button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messagesLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        )}
        {!messagesLoading && messages.length === 0 && (
          <div className="text-center text-xs text-muted-foreground py-8">
            No messages yet.
          </div>
        )}
        {!messagesLoading &&
          messages.map((msg) => (
            <ThreadBubble
              key={msg.id}
              msg={msg}
              canInteract={canInteract}
              optionPending={selectOption.isPending}
              onPickOption={handlePickOption}
            />
          ))}
        {agentTyping && canInteract && (
          <AgentTypingBubble agentId={thread.agent_id ?? 'Agent'} />
        )}
        <div ref={chatEndRef} />
      </div>

      {canInteract ? (
        <div className="p-4 border-t bg-card shrink-0">
          <div className="flex items-end gap-2 max-w-3xl mx-auto">
            <div className="flex-1 relative">
              <Input
                placeholder="Type your response... (Enter to send)"
                className="pr-10 h-9"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={addMessage.isPending}
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-muted-foreground hidden sm:block">
                ⏎
              </div>
            </div>
            <Button
              size="icon"
              className="shrink-0 h-9 w-9"
              onClick={handleSend}
              disabled={!draft.trim() || addMessage.isPending}
              title="Send"
            >
              {addMessage.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            </Button>
          </div>
        </div>
      ) : (
        <div className="p-3 border-t bg-muted/30 text-center text-xs text-muted-foreground shrink-0">
          Thread resolved · read-only
        </div>
      )}
    </>
  );
}
