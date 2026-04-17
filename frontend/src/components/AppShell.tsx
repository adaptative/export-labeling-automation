import React, { useState, useRef, useEffect } from 'react';
import { useAuthStore } from '../store/authStore';
import { useLocation, Link } from 'wouter';
import {
  Home, Layers, Settings, FileText, CheckSquare, AlertCircle,
  Users, Activity, BarChart, FileCode, Beaker, Archive, Lock,
  Database, ChevronDown, LogOut, Search,
} from 'lucide-react';
import { NotificationBell } from './NotificationBell';

interface AppShellProps {
  children: React.ReactNode;
}

interface MenuGroup {
  label: string;
  items: { href: string; icon: React.FC<{ className?: string }>; label: string }[];
}

const NAV_GROUPS: MenuGroup[] = [
  {
    label: 'Operations',
    items: [
      { href: '/orders', icon: Layers, label: 'Orders' },
      { href: '/documents', icon: FileText, label: 'Documents' },
      { href: '/hitl', icon: CheckSquare, label: 'HiTL Inbox' },
      { href: '/artifacts', icon: Archive, label: 'Artifacts' },
    ],
  },
  {
    label: 'Governance',
    items: [
      { href: '/rules', icon: FileCode, label: 'Compliance Rules' },
      { href: '/warning-labels', icon: AlertCircle, label: 'Warning Labels' },
      { href: '/importers', icon: Users, label: 'Importers' },
      { href: '/audit', icon: Database, label: 'Audit Log' },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { href: '/automation', icon: BarChart, label: 'Automation KPIs' },
      { href: '/agents', icon: Beaker, label: 'Agent Inspector' },
      { href: '/evals', icon: CheckSquare, label: 'Prompt Evals' },
      { href: '/cost', icon: Activity, label: 'Cost & Budgets' },
    ],
  },
  {
    label: 'Admin',
    items: [
      { href: '/admin/users', icon: Users, label: 'Users' },
      { href: '/admin/security', icon: Lock, label: 'Security' },
      { href: '/settings/profile', icon: Settings, label: 'Settings' },
      { href: '/settings/notifications', icon: AlertCircle, label: 'Notifications' },
    ],
  },
];

function Dropdown({ group, location }: { group: MenuGroup; location: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const isGroupActive = group.items.some(
    (item) => location === item.href || location.startsWith(item.href + '/')
  );

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-1 px-3 py-2 text-sm rounded-md transition-colors ${
          isGroupActive
            ? 'text-primary font-medium bg-primary/5'
            : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        }`}
      >
        {group.label}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 w-52 bg-popover border border-border rounded-lg shadow-lg py-1 z-50">
          {group.items.map((item) => {
            const Icon = item.icon;
            const active = location === item.href || location.startsWith(item.href + '/');
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
                  active
                    ? 'text-primary bg-primary/5 font-medium'
                    : 'text-popover-foreground hover:bg-muted'
                }`}
              >
                <Icon className="w-4 h-4 opacity-70" />
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AppShell({ children }: AppShellProps) {
  const { isAuthenticated, isSessionChecked, logout } = useAuthStore();
  const [location, setLocation] = useLocation();

  if (!isSessionChecked) {
    return null; // Wait for session verification
  }

  if (!isAuthenticated) {
    setLocation('/login');
    return null;
  }

  return (
    <div className="min-h-screen w-full flex flex-col bg-background text-foreground">
      <header className="h-14 border-b border-border bg-card flex items-center px-4 shrink-0 sticky top-0 z-20">
        <Link href="/" className="font-mono font-bold text-primary tracking-tight text-lg mr-1">
          Labelforge
        </Link>
        <div className="text-xs text-muted-foreground border-l border-border pl-3 ml-2 mr-4 hidden lg:block">
          <span className="font-medium text-foreground/70">Nakoda Art & Craft</span>
        </div>

        <nav className="flex items-center gap-0.5 ml-2">
          <Link
            href="/"
            className={`flex items-center gap-1.5 px-3 py-2 text-sm rounded-md transition-colors ${
              location === '/'
                ? 'text-primary font-medium bg-primary/5'
                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
            }`}
          >
            <Home className="w-4 h-4" />
            <span className="hidden md:inline">Dashboard</span>
          </Link>

          {NAV_GROUPS.map((group) => (
            <Dropdown key={group.label} group={group} location={location} />
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <div className="hidden md:flex items-center justify-center w-52 h-8 bg-muted rounded border border-border text-xs text-muted-foreground cursor-text">
            <Search className="w-3.5 h-3.5 mr-1.5 opacity-50" />
            <span>⌘K Search...</span>
          </div>
          <div className="flex items-center gap-1.5 bg-green-50 text-green-700 px-2 py-1 rounded text-xs border border-green-200">
            <div className="w-2 h-2 rounded-full bg-green-500" />
            <span className="font-medium hidden sm:inline">Healthy</span>
          </div>
          <NotificationBell />
          <button
            onClick={logout}
            className="text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-md hover:bg-muted"
            title="Sign out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </header>

      <main className="flex-1 overflow-auto bg-background">
        {children}
      </main>
    </div>
  );
}
