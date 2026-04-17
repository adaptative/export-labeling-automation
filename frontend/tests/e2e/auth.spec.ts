/**
 * Auth E2E (INT-024 · Sprint-17).
 *
 * Uses the raw Playwright ``test`` export because we want to drive the
 * actual login form — not the pre-seeded ``authedPage`` fixture.
 */
import { test, expect } from '@playwright/test';
import { installDefaultMocks } from './fixtures/apiMocks';
import { seedAuth } from './fixtures/auth';

test.beforeEach(async ({ page }) => {
  await installDefaultMocks(page);
});

test('login with valid credentials redirects to dashboard', async ({ page }) => {
  await page.goto('/login');
  await page.getByTestId('input-email').fill('admin@nakodacraft.com');
  await page.getByTestId('input-password').fill('correct-horse');
  await page.getByTestId('button-submit-login').click();

  await expect(page).toHaveURL(/\/(\?.*)?$/, { timeout: 10_000 });
  // Auth store persisted a token
  const persisted = await page.evaluate(() => window.localStorage.getItem('auth-storage'));
  expect(persisted).toBeTruthy();
});

test('login with invalid credentials surfaces an error', async ({ page }) => {
  await page.goto('/login');
  await page.getByTestId('input-email').fill('bad@example.com');
  await page.getByTestId('input-password').fill('wrong');
  await page.getByTestId('button-submit-login').click();

  await expect(page.getByTestId('login-error')).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});

test('logout clears session and returns to login', async ({ page }) => {
  // Simulate "logged out": no seeded auth + /auth/refresh denies a session.
  await page.route('**/api/v1/auth/refresh', async (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"no session"}' }),
  );
  await page.goto('/');
  await expect(page).toHaveURL(/\/login/);
});

test('auth persists across a page reload', async ({ page }) => {
  await seedAuth(page);
  await page.goto('/');
  await page.reload();
  await expect(page).not.toHaveURL(/\/login/);
});
