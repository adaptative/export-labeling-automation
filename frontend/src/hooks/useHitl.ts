import { useEffect, useRef, useState } from 'react';
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
 * thread detail query on status changes.
 */
export function useThreadLive(threadId: string | null) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const connRef = useRef<ReturnType<typeof openThreadLive> | null>(null);

  useEffect(() => {
    if (!threadId) return;
    setError(null);
    const conn = openThreadLive(threadId, {
      onMessage: (env: LiveEnvelope) => {
        if (env.type === 'hello') { setConnected(true); return; }
        if (env.type === 'agent_message' || env.type === 'human_message') {
          const msg = env.payload as HitlMessage;
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
        if (env.type === 'status_update' || env.type === 'thread_resolved' || env.type === 'escalation') {
          qc.invalidateQueries({ queryKey: ['hitl', 'thread', threadId] });
          qc.invalidateQueries({ queryKey: ['hitl', 'threads'] });
        }
      },
      onClose: () => { setConnected(false); },
      onError: () => { setError('Live connection dropped'); setConnected(false); },
    });
    connRef.current = conn;
    return () => {
      conn.unsubscribe();
      connRef.current = null;
      setConnected(false);
    };
  }, [threadId, qc]);

  return {
    connected,
    error,
    send: (frame: unknown) => connRef.current?.send(frame),
    sendTyping: () => connRef.current?.send({ type: 'typing', role: 'human' }),
    sendPing: () => connRef.current?.send({ type: 'ping' }),
  };
}
