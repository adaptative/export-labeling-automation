import { apiGet, apiPost, authFetch } from './authInterceptor';
import { useAuthStore } from '../store/authStore';

/**
 * HiTL API client (TASK-029 · Sprint-15).
 *
 * Wraps /api/v1/hitl for REST and /api/v1/hitl/threads/{id}/live for the
 * WebSocket live stream. Shapes mirror the backend pydantic models in
 * labelforge/api/v1/hitl.py.
 */

const API_BASE = '/api/v1';

// ── Types ────────────────────────────────────────────────────────────────

export type ThreadStatus = 'OPEN' | 'IN_PROGRESS' | 'RESOLVED' | 'ESCALATED';
export type Priority = 'P0' | 'P1' | 'P2';

export interface HitlMessage {
  id: string;
  role: 'agent' | 'human' | 'system';
  content: string;
  author_id: string | null;
  context: Record<string, unknown> | null;
  created_at: string;
}

export interface HitlThread {
  id: string;
  order_id: string | null;
  item_no: string | null;
  agent_id: string | null;
  priority: Priority;
  status: ThreadStatus;
  summary: string | null;
  blocking: string | null;
  sla_deadline: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  message_count: number;
  last_message_preview?: string | null;
}

export interface ThreadListResponse {
  threads: HitlThread[];
  total: number;
}

export interface CreateThreadRequest {
  order_id?: string | null;
  item_no?: string | null;
  agent_id?: string | null;
  priority?: Priority;
  summary?: string | null;
  blocking?: string | null;
  initial_message?: string | null;
  context?: Record<string, unknown>;
}

export interface AddMessageRequest {
  content: string;
  role?: 'agent' | 'human';
  author_id?: string | null;
  context?: Record<string, unknown>;
}

export interface OptionSelectRequest {
  option: string;
  context?: Record<string, unknown>;
}

export interface ResolveRequest {
  resolution_note?: string;
  resolved_by?: string;
}

export interface EscalateRequest {
  reason: string;
  escalated_by?: string;
}

// ── Discriminated envelope for WS frames ────────────────────────────────

export type LiveEnvelope =
  | { type: 'hello'; thread_id: string; payload: Record<string, unknown>; ts: string }
  | { type: 'agent_message' | 'human_message'; thread_id: string; payload: HitlMessage; ts: string }
  | { type: 'status_update'; thread_id: string; payload: { status: ThreadStatus }; ts: string }
  | { type: 'option_selected'; thread_id: string; payload: { option: string }; ts: string }
  | { type: 'typing'; thread_id: string; payload: { role: string }; ts: string }
  | { type: 'thread_resolved' | 'escalation'; thread_id: string; payload: Record<string, unknown>; ts: string }
  | { type: 'pong' | 'heartbeat'; thread_id?: string; payload?: Record<string, unknown>; ts: string }
  | { type: 'error'; payload: { message: string }; ts: string };

// ── REST ─────────────────────────────────────────────────────────────────

export interface ListThreadsParams {
  status?: ThreadStatus | 'all';
  priority?: Priority;
  order_id?: string;
  limit?: number;
  offset?: number;
}

// ── Backend-shape normalizers ────────────────────────────────────────────
//
// The FastAPI layer speaks the original ``HiTLThread`` / ``HiTLMessage``
// contract (``thread_id`` / ``message_id``).  The UI was built around the
// newer field name ``id`` plus a handful of enrichment fields
// (``summary`` / ``message_count`` / ``blocking`` / ``updated_at``) that the
// backend does not emit.  Rather than fork the API we normalize once, on
// the way in, so every component sees a consistent shape.

type BackendThread = {
  id?: string;
  thread_id?: string;
  order_id?: string | null;
  item_no?: string | null;
  agent_id?: string | null;
  priority?: Priority;
  status?: ThreadStatus;
  summary?: string | null;
  blocking?: string | null;
  sla_deadline?: string | null;
  created_at?: string;
  updated_at?: string;
  resolved_at?: string | null;
  message_count?: number;
  last_message_preview?: string | null;
};

type BackendMessage = {
  id?: string;
  message_id?: string;
  role?: 'agent' | 'human' | 'system';
  sender_type?: 'agent' | 'human' | 'system';
  content?: string;
  author_id?: string | null;
  context?: Record<string, unknown> | null;
  created_at?: string;
};

function normalizeThread(raw: BackendThread): HitlThread {
  const id = raw.id ?? raw.thread_id ?? '';
  // Fall back to a human-friendly synthetic summary when the backend
  // doesn't supply one — otherwise the sidebar degenerates into a wall
  // of "(no summary)" rows that are impossible to triage.
  const summary =
    raw.summary
    ?? (raw.agent_id && raw.item_no
      ? `${raw.agent_id} needs input · Item ${raw.item_no}`
      : raw.agent_id
        ? `${raw.agent_id} needs input`
        : null);
  return {
    id,
    order_id: raw.order_id ?? null,
    item_no: raw.item_no ?? null,
    agent_id: raw.agent_id ?? null,
    priority: (raw.priority ?? 'P2') as Priority,
    status: (raw.status ?? 'OPEN') as ThreadStatus,
    summary,
    blocking: raw.blocking ?? null,
    sla_deadline: raw.sla_deadline ?? null,
    created_at: raw.created_at ?? new Date().toISOString(),
    updated_at: raw.updated_at ?? raw.created_at ?? new Date().toISOString(),
    resolved_at: raw.resolved_at ?? null,
    message_count: raw.message_count ?? 0,
    last_message_preview: raw.last_message_preview ?? null,
  };
}

function normalizeMessage(raw: BackendMessage): HitlMessage {
  const role = raw.role ?? raw.sender_type ?? 'system';
  return {
    id: raw.id ?? raw.message_id ?? '',
    role: role as HitlMessage['role'],
    content: raw.content ?? '',
    author_id: raw.author_id ?? null,
    context: raw.context ?? null,
    created_at: raw.created_at ?? new Date().toISOString(),
  };
}

export async function listThreads(params: ListThreadsParams = {}): Promise<ThreadListResponse> {
  const q = new URLSearchParams();
  if (params.status && params.status !== 'all') q.set('status', params.status);
  if (params.priority) q.set('priority', params.priority);
  if (params.order_id) q.set('order_id', params.order_id);
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  const qs = q.toString();
  const raw = await apiGet<{ threads: BackendThread[]; total: number }>(
    `/hitl/threads${qs ? `?${qs}` : ''}`,
  );
  return {
    threads: (raw.threads ?? []).map(normalizeThread),
    total: raw.total ?? 0,
  };
}

export async function getThread(id: string): Promise<HitlThread & { messages: HitlMessage[] }> {
  const raw = await apiGet<{ thread?: BackendThread; messages?: BackendMessage[] } & BackendThread>(
    `/hitl/threads/${encodeURIComponent(id)}`,
  );
  // Backend returns ``{thread, messages}`` from the detail endpoint; tolerate
  // the flatter shape too in case the server layer ever changes.
  const threadRaw: BackendThread = raw.thread ?? (raw as BackendThread);
  const messages = (raw.messages ?? []).map(normalizeMessage);
  return { ...normalizeThread(threadRaw), messages };
}

export async function listMessages(
  id: string,
  params: { limit?: number; offset?: number } = {},
): Promise<{ messages: HitlMessage[]; total: number }> {
  const q = new URLSearchParams();
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  const qs = q.toString();
  const raw = await apiGet<{ messages: BackendMessage[]; total: number }>(
    `/hitl/threads/${encodeURIComponent(id)}/messages${qs ? `?${qs}` : ''}`,
  );
  return {
    messages: (raw.messages ?? []).map(normalizeMessage),
    total: raw.total ?? 0,
  };
}

export async function createThread(body: CreateThreadRequest): Promise<HitlThread> {
  const raw = await apiPost<BackendThread>('/hitl/threads', body);
  return normalizeThread(raw);
}

export async function addMessage(id: string, body: AddMessageRequest): Promise<HitlMessage> {
  // Backend expects ``sender_type`` and doesn't know the ``role`` key the UI
  // uses internally.  Translate on the way out.
  const payload = {
    sender_type: body.role ?? 'human',
    content: body.content,
    context: body.context,
  };
  const raw = await apiPost<BackendMessage>(
    `/hitl/threads/${encodeURIComponent(id)}/messages`,
    payload,
  );
  return normalizeMessage(raw);
}

export async function selectOption(id: string, body: OptionSelectRequest): Promise<HitlMessage> {
  // Backend signature is ``{option_index, option_value}``.  The UI hands us
  // ``{option: "<string>"}`` and expects us to look up the index from the
  // latest agent prompt — but since the backend only records
  // ``option_value`` anyway, we send 0 as the index and the string value.
  const payload = {
    option_index: 0,
    option_value: body.option,
  };
  const raw = await apiPost<BackendMessage>(
    `/hitl/threads/${encodeURIComponent(id)}/option-select`,
    payload,
  );
  return normalizeMessage(raw);
}

export async function resolveThread(
  id: string,
  body: ResolveRequest = {},
): Promise<{ thread_id: string; status: 'RESOLVED'; resolved_at: string }> {
  const payload = { note: body.resolution_note };
  const raw = await apiPost<{ thread: BackendThread; ok: boolean }>(
    `/hitl/threads/${encodeURIComponent(id)}/resolve`,
    payload,
  );
  const t = normalizeThread(raw.thread ?? {});
  return {
    thread_id: t.id,
    status: 'RESOLVED',
    resolved_at: t.resolved_at ?? t.updated_at,
  };
}

export async function escalateThread(
  id: string,
  body: EscalateRequest,
): Promise<{ thread_id: string; status: 'ESCALATED'; reason: string }> {
  const raw = await apiPost<{ thread: BackendThread; ok: boolean }>(
    `/hitl/threads/${encodeURIComponent(id)}/escalate`,
    body,
  );
  const t = normalizeThread(raw.thread ?? {});
  return { thread_id: t.id, status: 'ESCALATED', reason: body.reason };
}

// ── WebSocket helper ─────────────────────────────────────────────────────

/**
 * Open a live WebSocket connection for a thread.
 *
 * Returns an object with an `unsubscribe()` closer. The socket auto-
 * authenticates via the access token in the auth store and passes it as
 * ``?token=`` (matching the backend's query-param auth pattern).
 */
export function openThreadLive(
  threadId: string,
  handlers: {
    onMessage: (env: LiveEnvelope) => void;
    onError?: (err: Event) => void;
    onClose?: (ev: CloseEvent) => void;
  },
): { ws: WebSocket; unsubscribe: () => void; send: (msg: unknown) => void } {
  const token = useAuthStore.getState().accessToken ?? '';
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}${API_BASE}/hitl/threads/${encodeURIComponent(threadId)}/live?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(url);

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as LiveEnvelope;
      handlers.onMessage(data);
    } catch {
      // ignore malformed frame
    }
  };
  if (handlers.onError) ws.onerror = handlers.onError;
  if (handlers.onClose) ws.onclose = handlers.onClose;

  return {
    ws,
    unsubscribe: () => {
      // Calling ``close()`` on a socket that is still in CONNECTING
      // state produces a loud "WebSocket closed without opened" error
      // in every browser console. Defer the close until ``onopen``
      // fires (or skip it entirely if the socket already finished
      // opening/closing).
      try {
        if (ws.readyState === WebSocket.CONNECTING) {
          ws.addEventListener('open', () => {
            try { ws.close(); } catch { /* no-op */ }
          }, { once: true });
        } else if (
          ws.readyState === WebSocket.OPEN
          // ``CLOSING`` and ``CLOSED`` are no-ops
        ) {
          ws.close();
        }
      } catch { /* no-op */ }
    },
    send: (msg) => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
    },
  };
}
