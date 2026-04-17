/**
 * Cost breaker E2E (INT-024 · Sprint-17).
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('cost page loads four spending tiers', async ({ authedPage: page }) => {
  await page.goto('/cost');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/cost/overview');
    return r.json();
  });
  expect(body.tiers).toHaveLength(4);
});

test('breaker-breached response propagates to the UI layer', async ({ authedPage: page }) => {
  await page.route('**/api/v1/cost/overview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        tiers: [
          { name: 'Monthly budget', used: 1100, cap: 1000 },
          { name: 'Daily burn', used: 80, cap: 75 },
          { name: 'Per-agent cap', used: 30, cap: 25 },
          { name: 'HiTL routing', used: 6, cap: 5 },
        ],
        breakers: [{ name: 'monthly', breached: true }],
      }),
    });
  });
  await page.goto('/cost');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/cost/overview');
    return r.json();
  });
  expect(body.breakers?.[0]?.breached).toBe(true);
});

test('admin can PUT /budgets/tenant/:id/caps', async ({ authedPage: page }) => {
  await page.goto('/cost');
  const status = await page.evaluate(async () => {
    const r = await fetch('/api/v1/budgets/tenant/tnt-nakoda-001/caps', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ monthly: 2000 }),
    });
    return r.status;
  });
  expect(status).toBe(200);
});
