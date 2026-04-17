import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  getNotificationPreferences,
  listNotifications,
  markAllAsRead,
  markAsRead,
  openNotificationsLive,
  updateNotificationPreferences,
  type EventPreference,
  type ListNotificationsParams,
  type Notification,
  type NotificationListResponse,
  type NotificationLiveEnvelope,
  notificationTypeLabel,
} from '@/api/notifications';

const NOTIFICATIONS_KEY = ['notifications'] as const;
const PREFS_KEY = ['notifications', 'preferences'] as const;

export function useNotifications(params: ListNotificationsParams = {}) {
  return useQuery({
    queryKey: [...NOTIFICATIONS_KEY, params],
    queryFn: () => listNotifications(params),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
  });
}

export function useMarkNotificationAsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => markAsRead(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }); },
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => markAllAsRead(),
    onSuccess: () => { qc.invalidateQueries({ queryKey: NOTIFICATIONS_KEY }); },
  });
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: PREFS_KEY,
    queryFn: () => getNotificationPreferences(),
    staleTime: 60_000,
  });
}

export function useUpdateNotificationPreferences() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (preferences: EventPreference[]) => updateNotificationPreferences(preferences),
    onSuccess: () => { qc.invalidateQueries({ queryKey: PREFS_KEY }); },
  });
}

/**
 * Keep an open WebSocket to /notifications/live while the hook is mounted.
 *
 * - Inserts pushed notifications into the list query cache so the bell
 *   badge updates without a refetch.
 * - Raises a Sonner toast for high-priority (critical/error) events and a
 *   subtle info toast for lower-severity events.
 */
export function useNotificationLive(enabled: boolean = true) {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const connRef = useRef<ReturnType<typeof openNotificationsLive> | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const conn = openNotificationsLive({
      onMessage: (env: NotificationLiveEnvelope) => {
        if (env.type === 'hello') { setConnected(true); return; }
        if (env.type === 'notification_received') {
          const notif = env.payload;
          qc.setQueriesData<NotificationListResponse | undefined>(
            { queryKey: NOTIFICATIONS_KEY },
            (prev) => {
              if (!prev) return prev;
              if (prev.notifications.some((n) => n.id === notif.id)) return prev;
              return {
                ...prev,
                notifications: [notif, ...prev.notifications],
                total: prev.total + 1,
                unread_count: prev.unread_count + (notif.read ? 0 : 1),
              };
            },
          );

          const label = notificationTypeLabel(notif.type);
          switch (notif.severity) {
            case 'critical':
            case 'error':
              toast.error(notif.title, { description: label, duration: 5_000 });
              break;
            case 'warning':
              toast.warning(notif.title, { description: label, duration: 5_000 });
              break;
            case 'info':
              toast.info(notif.title, { description: label, duration: 3_000 });
              break;
            default:
              toast(notif.title, { description: label, duration: 3_000 });
          }
          return;
        }
        if (env.type === 'notification_read') {
          qc.setQueriesData<NotificationListResponse | undefined>(
            { queryKey: NOTIFICATIONS_KEY },
            (prev) => {
              if (!prev) return prev;
              const notifications = prev.notifications.map((n) =>
                n.id === env.payload.id ? { ...n, read: true } : n,
              );
              const unread = notifications.filter((n) => !n.read).length;
              return { ...prev, notifications, unread_count: unread };
            },
          );
        }
      },
      onClose: () => { setConnected(false); },
      onError: () => { setConnected(false); },
    });
    connRef.current = conn;
    return () => {
      conn.unsubscribe();
      connRef.current = null;
      setConnected(false);
    };
  }, [enabled, qc]);

  return { connected, ping: () => connRef.current?.ping() };
}
