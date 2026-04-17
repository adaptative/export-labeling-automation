import { apiGet, apiPut } from './authInterceptor';
import { useAuthStore } from '../store/authStore';

/**
 * Notifications API client (INT-023 · Sprint-15).
 *
 * REST: /api/v1/notifications (+ /read-all, /{id}/read)
 * Preferences: /api/v1/users/me/notification-preferences
 * WebSocket: /api/v1/notifications/live
 */

const API_BASE = '/api/v1';

// ── Types ────────────────────────────────────────────────────────────────

export interface Notification {
  id: string;
  type: string;          // event type — cost_breaker.triggered, hitl.escalated, etc.
  title: string;
  message: string;
  severity: string;      // critical | error | warning | info
  order_id: string | null;
  item_no: string | null;
  read: boolean;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: Notification[];
  total: number;
  unread_count: number;
}

export interface ChannelPref {
  email: boolean;
  slack: boolean;
  pagerduty: boolean;
  in_app: boolean;
}

export interface EventPreference {
  event_type: string;
  enabled: boolean;
  channels: ChannelPref;
}

export interface NotificationPreferencesResponse {
  event_types: string[];
  channels: string[];
  preferences: EventPreference[];
}

export interface ListNotificationsParams {
  severity?: string;
  read?: boolean;
  order_id?: string;
  limit?: number;
  offset?: number;
}

// ── REST ─────────────────────────────────────────────────────────────────

export function listNotifications(
  params: ListNotificationsParams = {},
): Promise<NotificationListResponse> {
  const q = new URLSearchParams();
  if (params.severity) q.set('severity', params.severity);
  if (params.read != null) q.set('read', String(params.read));
  if (params.order_id) q.set('order_id', params.order_id);
  if (params.limit != null) q.set('limit', String(params.limit));
  if (params.offset != null) q.set('offset', String(params.offset));
  const qs = q.toString();
  return apiGet(`/notifications${qs ? `?${qs}` : ''}`);
}

export function markAsRead(id: string): Promise<{ id: string; read: boolean }> {
  return apiPut(`/notifications/${encodeURIComponent(id)}/read`);
}

export function markAllAsRead(): Promise<{ marked: number }> {
  return apiPut(`/notifications/read-all`);
}

export function getNotificationPreferences(): Promise<NotificationPreferencesResponse> {
  return apiGet('/users/me/notification-preferences');
}

export function updateNotificationPreferences(
  preferences: EventPreference[],
): Promise<NotificationPreferencesResponse> {
  return apiPut('/users/me/notification-preferences', { preferences });
}

// ── WebSocket ────────────────────────────────────────────────────────────

export type NotificationLiveEnvelope =
  | { type: 'hello'; payload: { user_id: string; tenant_id: string }; ts: string }
  | { type: 'notification_received'; payload: Notification; ts: string }
  | { type: 'notification_read'; payload: { id: string }; ts: string }
  | { type: 'heartbeat'; ts: string }
  | { type: 'pong'; ts: string };

export function openNotificationsLive(handlers: {
  onMessage: (env: NotificationLiveEnvelope) => void;
  onError?: (err: Event) => void;
  onClose?: (ev: CloseEvent) => void;
}): { ws: WebSocket; unsubscribe: () => void; ping: () => void } {
  const token = useAuthStore.getState().accessToken ?? '';
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${window.location.host}${API_BASE}/notifications/live?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(url);

  ws.onmessage = (ev) => {
    try {
      const data = JSON.parse(ev.data) as NotificationLiveEnvelope;
      handlers.onMessage(data);
    } catch {
      /* ignore malformed frame */
    }
  };
  if (handlers.onError) ws.onerror = handlers.onError;
  if (handlers.onClose) ws.onclose = handlers.onClose;

  return {
    ws,
    unsubscribe: () => { try { ws.close(); } catch { /* no-op */ } },
    ping: () => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
    },
  };
}

// ── Helpers ──────────────────────────────────────────────────────────────

export function severityColor(severity: string): string {
  switch (severity) {
    case 'critical':
    case 'error':
      return 'text-red-600 bg-red-50 border-red-200';
    case 'warning':
      return 'text-orange-600 bg-orange-50 border-orange-200';
    case 'info':
      return 'text-blue-600 bg-blue-50 border-blue-200';
    default:
      return 'text-gray-600 bg-gray-50 border-gray-200';
  }
}

export function notificationTypeLabel(type: string): string {
  const map: Record<string, string> = {
    'cost_breaker.triggered': 'Cost breaker breached',
    'hitl.escalated': 'HiTL escalation',
    'hitl.sla_breached': 'HiTL SLA breached',
    'order.completed': 'Order completed',
    'order.failed': 'Order failed',
    'pipeline.failure': 'Pipeline failure',
    'importer.invited': 'New importer invited',
    'system.alert': 'System alert',
  };
  return map[type] ?? type;
}
