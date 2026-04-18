import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  addMessage,
  createThread,
  escalateThread,
  getThread,
  listMessages,
  listThreads,
  openThreadLive,
  resolveThread,
  selectOption,
  type AddMessageRequest,
  type CreateThreadRequest,
  type EscalateRequest,
  type HitlMessage,
  type HitlThread,
  type ListThreadsParams,
  type OptionSelectRequest,
  type ResolveRequest,
  type LiveEnvelope,
} from '@/api/hitl';

const STALE_TIME = 5_000;

export function useThreads(params: ListThreadsParams = {}) {
  return useQuery({
    queryKey: ['hitl', 'threads', params],
    queryFn: () => listThreads(params),
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });
}

export function useThread(id: string | null) {
  return useQuery({
    queryKey: ['hitl', 'thread', id],
    queryFn: () => getThread(id!),
    enabled: !!id,
    staleTime: STALE_TIME,
  });
}

export function useThreadMessages(id: string | null) {
  return useQuery({
    queryKey: ['hitl', 'messages', id],
    queryFn: () => listMessages(id!, { limit: 200 }),
    enabled: !!id,
    staleTime: STALE_TIME,
  });
}

export function useCreateThread() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateThreadRequest) => createThread(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['hitl', 'threads'] }); },
  });
}

export function useAddMessage(threadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AddMessageRequest) => addMessage(threadId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl', 'messages', threadId] });
      qc.invalidateQueries({ queryKey: ['hitl', 'thread', threadId] });
      qc.invalidateQueries({ queryKey: ['hitl', 'threads'] });
    },
  });
}

export function useSelectOption(threadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: OptionSelectRequest) => selectOption(threadId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl', 'messages', threadId] });
      qc.invalidateQueries({ queryKey: ['hitl', 'thread', threadId] });
    },
  });
}

export function useResolveThread(threadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ResolveRequest = {}) => resolveThread(threadId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl'] });
    },
  });
}

export function useEscalateThread(threadId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EscalateRequest) => escalateThread(threadId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['hitl'] });
    },
  });
}

/**
 * Subscribe to the server-pushed live stream for a thread.
 *
 * Appends new agent/human messages to the cached list and invalidates the
 * thread detail query on status changes. Also tracks:
 *
 * - ``agentTyping`` — true while the backend dispatcher is waiting on the
 *   LLM for this thread. Flipped on by a ``{type:"typing", role:"agent",
 *   state:"start"}`` envelope, off by ``state:"stop"`` or a real
 *   ``agent_message``. Auto-clears after 20 s as a safety belt in case
 *   the "stop" frame is lost (e.g. backend crash mid-completion).
 */
// Max time we keep the "agent is typing" indicator shown without a fresh
// heartbeat from the backend. If the dispatcher crashes mid-LLM call, we
// don't want the UI to pin "agent thinking…" forever.
const AGENT_TYPING_TIMEOUT_MS = 20_000;

export function useThreadLive(threadId: string | null) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentTyping, setAgentTyping] = useState(false);
  const connRef = useRef<ReturnType<typeof openThreadLive> | null>(null);
  const typingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!threadId) return;
    setError(null);

    const clearTypingTimer = () => {
      if (typingTimerRef.current !== null) {
        clearTimeout(typingTimerRef.current);
        typingTimerRef.current = null;
      }
    };
    const stopAgentTyping = () => {
      clearTypingTimer();
      setAgentTyping(false);
    };
    const startAgentTyping = () => {
      setAgentTyping(true);
      clearTypingTimer();
      typingTimerRef.current = setTimeout(stopAgentTyping, AGENT_TYPING_TIMEOUT_MS);
    };

    const conn = openThreadLive(threadId, {
      onMessage: (env: LiveEnvelope) => {
        if (env.type === 'hello') { setConnected(true); return; }
        if (env.type === 'agent_message' || env.type === 'human_message') {
          const msg = env.payload as HitlMessage;
          // A real agent reply implicitly ends the "typing" state.
          if (env.type === 'agent_message') stopAgentTyping();
          qc.setQueryData<{ messages: HitlMessage[]; total: number } | undefined>(
            ['hitl', 'messages', threadId],
            (prev) => {
              if (!prev) return prev;
              if (prev.messages.some((m) => m.id === msg.id)) return prev;
              return { messages: [...prev.messages, msg], total: prev.total + 1 };
            },
          );
          return;
        }
        if (env.type === 'typing') {
          // Only react to agent typing — the human's own keystroke echoes
          // shouldn't render a "typing…" bubble for themselves.
          const role = (env.payload as { role?: string } | undefined)?.role;
          const state = (env.payload as { state?: string } | undefined)?.state;
          if (role !== 'agent') return;
          if (state === 'stop') stopAgentTyping();
          else startAgentTyping();
          return;
        }
        if (env.type === 'status_update' || env.type === 'thread_resolved' || env.type === 'escalation') {
          // Thread went terminal or status changed — drop the indicator.
          if (env.type === 'thread_resolved' || env.type === 'escalation') {
            stopAgentTyping();
          }
          qc.invalidateQueries({ queryKey: ['hitl', 'thread', threadId] });
          qc.invalidateQueries({ queryKey: ['hitl', 'threads'] });
        }
      },
      onClose: () => { setConnected(false); stopAgentTyping(); },
      onError: () => {
        setError('Live connection dropped');
        setConnected(false);
        stopAgentTyping();
      },
    });
    connRef.current = conn;
    return () => {
      conn.unsubscribe();
      connRef.current = null;
      setConnected(false);
      clearTypingTimer();
      setAgentTyping(false);
    };
  }, [threadId, qc]);

  return {
    connected,
    error,
    agentTyping,
    send: (frame: unknown) => connRef.current?.send(frame),
    sendTyping: () => connRef.current?.send({ type: 'typing', role: 'human' }),
    sendPing: () => connRef.current?.send({ type: 'ping' }),
  };
}

/**
 * Subscribe to typing events for an arbitrary set of threads and track
 * per-thread agent-typing state. Used by the Order Detail → Issues tab,
 * which renders many threads at once and can't mount a full
 * ``useThreadLive`` per card without a large refactor.
 *
 * Connections are maintained *incrementally*: when the caller expands a
 * new card we open one WS, when they collapse it we close one WS.
 * Rebuilding the whole set on every change would close-then-reopen every
 * socket — and if an upstream proxy is slow to answer the upgrade,
 * closing a socket whose handshake is still in flight produces a loud
 * "WebSocket closed without opened" error in the console.
 */
export function useAgentTypingByThread(threadIds: string[]) {
  // Stable stringification of the incoming list so effect identity only
  // changes when the *set* of ids actually changes (not on every render
  // where the caller passes a freshly-built array).
  const key = useMemo(
    () => [...threadIds].sort().join('|'),
    [threadIds],
  );
  const [typingByThread, setTypingByThread] = useState<Record<string, boolean>>({});

  // Persistent caches across effect runs so we can diff adds/removes
  // instead of tearing everything down each time.
  const connsRef = useRef<Record<string, ReturnType<typeof openThreadLive>>>({});
  const timersRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  useEffect(() => {
    const next = new Set(key ? key.split('|').filter(Boolean) : []);
    const conns = connsRef.current;
    const timers = timersRef.current;

    const clearTimer = (id: string) => {
      if (timers[id]) { clearTimeout(timers[id]); delete timers[id]; }
    };
    const setTyping = (id: string, val: boolean) => {
      setTypingByThread((prev) => {
        if (prev[id] === val) return prev;
        return { ...prev, [id]: val };
      });
    };

    // 1. Close connections for threads that are no longer expanded.
    for (const id of Object.keys(conns)) {
      if (next.has(id)) continue;
      try { conns[id].unsubscribe(); } catch { /* no-op */ }
      delete conns[id];
      clearTimer(id);
      setTyping(id, false);
    }

    // 2. Open connections for newly-expanded threads.
    for (const id of next) {
      if (conns[id]) continue;
      conns[id] = openThreadLive(id, {
        onMessage: (env: LiveEnvelope) => {
          if (env.type === 'agent_message') {
            clearTimer(id);
            setTyping(id, false);
            return;
          }
          if (env.type === 'typing') {
            const role = (env.payload as { role?: string } | undefined)?.role;
            const state = (env.payload as { state?: string } | undefined)?.state;
            if (role !== 'agent') return;
            if (state === 'stop') {
              clearTimer(id);
              setTyping(id, false);
            } else {
              setTyping(id, true);
              clearTimer(id);
              timers[id] = setTimeout(
                () => setTyping(id, false),
                AGENT_TYPING_TIMEOUT_MS,
              );
            }
            return;
          }
          if (env.type === 'thread_resolved' || env.type === 'escalation') {
            clearTimer(id);
            setTyping(id, false);
          }
        },
        onClose: () => { clearTimer(id); setTyping(id, false); },
        onError: () => { clearTimer(id); setTyping(id, false); },
      });
    }
    // No cleanup returned — we want connections to persist across effect
    // runs. The unmount cleanup is handled separately below.
  }, [key]);

  // Tear everything down on unmount of the consuming component.
  useEffect(() => {
    return () => {
      for (const conn of Object.values(connsRef.current)) {
        try { conn.unsubscribe(); } catch { /* no-op */ }
      }
      for (const t of Object.values(timersRef.current)) clearTimeout(t);
      connsRef.current = {};
      timersRef.current = {};
    };
  }, []);

  return typingByThread;
}
