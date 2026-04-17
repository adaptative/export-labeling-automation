import React, { useMemo, useState } from 'react';
import { Bell, Check, CheckCheck, AlertCircle, AlertTriangle, Info, Zap } from 'lucide-react';
import { formatDistanceToNow } from 'date-fns';
import { Link } from 'wouter';
import {
  Popover, PopoverTrigger, PopoverContent,
} from '@/components/ui/popover';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import {
  useMarkAllNotificationsRead,
  useMarkNotificationAsRead,
  useNotificationLive,
  useNotifications,
} from '@/hooks/useNotifications';
import { notificationTypeLabel, type Notification } from '@/api/notifications';

/**
 * Notification bell + dropdown panel (INT-023).
 *
 * - Subscribes to /notifications/live while the header is mounted so the
 *   badge updates in real time.
 * - Click an item → mark read + navigate to the relevant resource (if we
 *   have an order_id).
 */

function severityIcon(severity: string) {
  switch (severity) {
    case 'critical':
    case 'error':
      return <AlertCircle className="w-4 h-4 text-red-500" />;
    case 'warning':
      return <AlertTriangle className="w-4 h-4 text-orange-500" />;
    case 'info':
      return <Info className="w-4 h-4 text-blue-500" />;
    default:
      return <Zap className="w-4 h-4 text-muted-foreground" />;
  }
}

function NotificationItem({
  notif,
  onClick,
}: {
  notif: Notification;
  onClick: () => void;
}) {
  const href = notif.order_id ? `/orders/${notif.order_id}` : undefined;
  const body = (
    <div
      onClick={onClick}
      className={`flex gap-3 px-3 py-2.5 cursor-pointer border-b hover:bg-muted/40 ${
        notif.read ? 'opacity-70' : 'bg-primary/5'
      }`}
    >
      <div className="shrink-0 mt-0.5">{severityIcon(notif.severity)}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium truncate">{notif.title}</span>
          {!notif.read && <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />}
        </div>
        <div className="text-xs text-muted-foreground line-clamp-2">
          {notif.message || notificationTypeLabel(notif.type)}
        </div>
        <div className="flex items-center gap-2 mt-1 text-[10px] text-muted-foreground">
          <span>{notificationTypeLabel(notif.type)}</span>
          <span>·</span>
          <span>
            {formatDistanceToNow(new Date(notif.created_at), { addSuffix: true })}
          </span>
          {notif.order_id && (
            <>
              <span>·</span>
              <span className="font-mono">{notif.order_id}</span>
            </>
          )}
        </div>
      </div>
    </div>
  );
  return href ? (
    <Link href={href} onClick={onClick}>
      {body}
    </Link>
  ) : (
    body
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useNotifications({ limit: 10 });
  const markRead = useMarkNotificationAsRead();
  const markAll = useMarkAllNotificationsRead();

  // Always-on live connection while the shell is mounted (not just while
  // the panel is open) so the badge updates immediately.
  useNotificationLive(true);

  const unread = data?.unread_count ?? 0;
  const notifications = data?.notifications ?? [];

  const handleClick = (notif: Notification) => {
    if (!notif.read) markRead.mutate(notif.id);
    setOpen(false);
  };

  const badgeClass = useMemo(() => {
    if (unread === 0) return 'hidden';
    if (unread > 9) return 'h-5 min-w-5 px-1';
    return 'h-4 min-w-4';
  }, [unread]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="relative p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label={`Notifications${unread ? ` (${unread} unread)` : ''}`}
        >
          <Bell className="w-4 h-4" />
          {unread > 0 && (
            <span
              className={`absolute -top-0.5 -right-0.5 bg-red-500 text-white text-[10px] font-medium rounded-full flex items-center justify-center ${badgeClass}`}
            >
              {unread > 9 ? '9+' : unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0" sideOffset={8}>
        <div className="flex items-center justify-between px-3 py-2 border-b">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">Notifications</span>
            {unread > 0 && (
              <Badge variant="secondary" className="h-4 px-1.5 text-[10px]">
                {unread} new
              </Badge>
            )}
          </div>
          {unread > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => markAll.mutate()}
              disabled={markAll.isPending}
            >
              <CheckCheck className="w-3.5 h-3.5 mr-1" />
              Mark all read
            </Button>
          )}
        </div>
        <ScrollArea className="max-h-[60vh]">
          {isLoading && (
            <div className="p-6 text-center text-xs text-muted-foreground">
              Loading notifications…
            </div>
          )}
          {!isLoading && notifications.length === 0 && (
            <div className="p-8 text-center">
              <Bell className="w-8 h-8 text-muted-foreground/30 mx-auto mb-2" />
              <p className="text-sm text-muted-foreground">You're all caught up.</p>
              <p className="text-[11px] text-muted-foreground mt-1">
                New alerts will appear here in real time.
              </p>
            </div>
          )}
          {!isLoading &&
            notifications.map((n) => (
              <NotificationItem key={n.id} notif={n} onClick={() => handleClick(n)} />
            ))}
        </ScrollArea>
        <div className="border-t px-3 py-2 flex items-center justify-between text-[11px]">
          <Link
            href="/settings/notifications"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => setOpen(false)}
          >
            Notification preferences
          </Link>
          {data?.total != null && (
            <span className="text-muted-foreground">{data.total} total</span>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
