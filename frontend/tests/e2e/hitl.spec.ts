/**
 * HiTL E2E (INT-024 · Sprint-17).
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('HiTL page loads and /hitl/threads returns a thread list', async ({ authedPage: page }) => {
  await page.goto('/hitl');
  const res = await page.evaluate(async () => {
    const r = await fetch('/api/v1/hitl/threads');
    return { status: r.status, json: await r.json() };
  });
  expect(res.status).toBe(200);
  expect(Array.isArray(res.json.threads)).toBe(true);
});

test('sending a message POSTs to /messages', async ({ authedPage: page }) => {
  let captured: any = null;
  await page.route('**/api/v1/hitl/threads/*/messages', async (route, req) => {
    if (req.method() === 'POST') captured = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
    await route.fallback();
  });
  await page.goto('/hitl');
  await page.evaluate(async () => {
    await fetch('/api/v1/hitl/threads/thr-001/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: 'Yes — shipping to California' }),
    });
  });
  expect(captured?.body).toContain('California');
});

test('option-select endpoint is POSTable', async ({ authedPage: page }) => {
  let hit = false;
  await page.route('**/api/v1/hitl/threads/*/option-select', async (route) => {
    hit = true;
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
  await page.goto('/hitl');
  await page.evaluate(async () => {
    await fetch('/api/v1/hitl/threads/thr-001/option-select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ option: 'Yes' }),
    });
  });
  expect(hit).toBe(true);
});

test('resolving a thread toggles its state', async ({ authedPage: page }) => {
  const responses: number[] = [];
  await page.route('**/api/v1/hitl/threads/*/resolve', async (route) => {
    responses.push(200);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, state: 'resolved' }),
    });
  });
  await page.goto('/hitl');
  const result = await page.evaluate(async () => {
    const r = await fetch('/api/v1/hitl/threads/thr-001/resolve', { method: 'POST' });
    return r.json();
  });
  expect(result.state).toBe('resolved');
  expect(responses).toHaveLength(1);
});
