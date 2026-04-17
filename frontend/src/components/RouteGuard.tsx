import React from 'react';
import { Redirect } from 'wouter';
import { useAuthStore } from '../store/authStore';
import type { Role } from '../lib/types';

interface RouteGuardProps {
  children: React.ReactNode;
}

/**
 * Redirects unauthenticated users to /login.
 * Waits for session verification before deciding.
 */
export function RouteGuard({ children }: RouteGuardProps) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isSessionChecked = useAuthStore((s) => s.isSessionChecked);

  if (!isSessionChecked) {
    return null; // Wait for verifySession to complete
  }

  if (!isAuthenticated) {
    return <Redirect to="/login" />;
  }

  return <>{children}</>;
}

interface RoleGuardProps {
  children: React.ReactNode;
  allowedRoles: Role[];
  fallback?: string;
}

/**
 * Only renders children if the user has one of the allowed roles.
 * Redirects to fallback (default: /) if role doesn't match.
 */
export function RoleGuard({ children, allowedRoles, fallback = '/' }: RoleGuardProps) {
  const role = useAuthStore((s) => s.role);

  if (!role || !allowedRoles.includes(role)) {
    return <Redirect to={fallback} />;
  }

  return <>{children}</>;
}

/**
 * Admin-only guard.
 */
export function AdminGuard({ children }: RouteGuardProps) {
  return (
    <RoleGuard allowedRoles={['Admin']}>
      {children}
    </RoleGuard>
  );
}

/**
 * Importer QA guard — restricted to portal pages.
 */
export function ImporterGuard({ children }: RouteGuardProps) {
  return (
    <RoleGuard allowedRoles={['Importer QA']} fallback="/portal/importer">
      {children}
    </RoleGuard>
  );
}
