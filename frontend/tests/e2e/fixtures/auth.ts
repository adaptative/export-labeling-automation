/**
 * Auth fixture for Playwright tests (INT-024 · Sprint-17).
 *
 * Extends the base ``test`` with a pre-authenticated ``Page`` by seeding
 * the Zustand ``auth-storage`` entry in ``localStorage`` before the app
 * boots. This sidesteps the real ``/auth/login`` round-trip so tests
 * focused on non-auth journeys do not depend on a live backend.
 *
 * Tests that *do* exercise the real login form use the base ``test``
 * export from ``@playwright/test`` directly.
 */
import { test as base, expect, type Page } from '@playwright/test';

export interface SeededUser {
  id: string;
  email: string;
  name: string;
  tenant_id: string;
  role: 'ADMIN' | 'OPERATOR' | 'VIEWER';
  display_name?: string;
}

export const DEFAULT_USER: SeededUser = {
  id: 'usr-admin-001',
  email: 'admin@nakodacraft.com',
  name: 'Admin Nakoda',
  display_name: 'Admin Nakoda',
  tenant_id: 'tnt-nakoda-001',
  role: 'ADMIN',
};

// A deterministic JWT payload that our auth store accepts as "logged in".
// The Zustand persist middleware reads this key on hydrate and the
// RouteGuard treats ``isAuthenticated + non-expired token`` as authorised.
export function buildSeededAuthState(user: SeededUser = DEFAULT_USER) {
  const expiresAt = Date.now() + 60 * 60 * 1000; // 1h
  return {
    state: {
      user: {
        id: user.id,
        email: user.email,
        name: user.display_name ?? user.name,
        tenant_id: user.tenant_id,
        role: user.role,
      },
      role: user.role,
      isAuthenticated: true,
      isSessionChecked: true,
      accessToken: `stub-token.${user.id}.${expiresAt}`,
      expiresAt,
      isLoading: false,
      error: null,
    },
    version: 0,
  };
}

export async function seedAuth(page: Page, user: SeededUser = DEFAULT_USER): Promise<void> {
  const payload = JSON.stringify(buildSeededAuthState(user));
  // Use addInitScript so the value is present *before* React hydrates.
  await page.addInitScript((raw) => {
    window.localStorage.setItem('auth-storage', raw);
  }, payload);
}

export type Fixtures = {
  authedPage: Page;
  user: SeededUser;
};

export const test = base.extend<Fixtures>({
  user: async ({}, use) => {
    await use(DEFAULT_USER);
  },
  authedPage: async ({ page, user }, use) => {
    await seedAuth(page, user);
    await use(page);
  },
});

export { expect };
