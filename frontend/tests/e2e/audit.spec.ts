/**
 * Audit-log E2E (INT-024 · Sprint-17).
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('audit page loads events', async ({ authedPage: page }) => {
  await page.goto('/audit');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/audit');
    return r.json();
  });
  expect(body.events.length).toBeGreaterThan(0);
});

test('filter by actor_type narrows results', async ({ authedPage: page }) => {
  await page.goto('/audit');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/audit?actor_type=agent');
    return r.json();
  });
  expect(body.events.every((e: any) => e.actor_type === 'agent')).toBe(true);
});

test('filter by action narrows results', async ({ authedPage: page }) => {
  await page.goto('/audit');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/audit?action=order.create');
    return r.json();
  });
  expect(body.events.every((e: any) => e.action === 'order.create')).toBe(true);
});

test('empty-filter combination returns an empty list, not an error', async ({ authedPage: page }) => {
  await page.goto('/audit');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/audit?actor_type=nonexistent');
    return r.json();
  });
  expect(body.events).toEqual([]);
});
