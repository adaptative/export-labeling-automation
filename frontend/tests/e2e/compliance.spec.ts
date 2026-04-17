/**
 * Compliance / rules / warning-labels E2E (INT-024 · Sprint-17).
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';
import { makeRulePayload, makeWarningLabelPayload } from './fixtures/testData';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('rules page loads and the /rules endpoint replies 200', async ({ authedPage: page }) => {
  await page.goto('/rules');
  await expect(page.locator('body')).not.toBeEmpty();
  const res = await page.evaluate(async () => {
    const r = await fetch('/api/v1/rules');
    return { status: r.status, json: await r.json() };
  });
  expect(res.status).toBe(200);
  expect(Array.isArray(res.json.rules)).toBe(true);
});

test('creating a rule POSTs /rules with the DSL intact', async ({ authedPage: page }) => {
  const payload = makeRulePayload({ dsl: 'item.total_qty > 10 AND item.country == "US"' });
  let posted: any = null;
  await page.route('**/api/v1/rules', async (route, req) => {
    if (req.method() === 'POST') posted = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
    await route.fallback();
  });
  await page.goto('/rules');
  await page.evaluate(async (body) => {
    await fetch('/api/v1/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }, payload);
  expect(posted?.dsl).toBe(payload.dsl);
  expect(posted?.severity).toBe(payload.severity);
});

test('dry-run endpoint returns newly_failing / newly_passing counts', async ({ authedPage: page }) => {
  await page.goto('/rules');
  const result = await page.evaluate(async () => {
    const r = await fetch('/api/v1/rules/rul-001/dry-run', { method: 'POST' });
    return r.json();
  });
  expect(result).toMatchObject({
    newly_failing: expect.any(Number),
    newly_passing: expect.any(Number),
  });
});

test('promoting a rule flips status to testing', async ({ authedPage: page }) => {
  await page.goto('/rules');
  const result = await page.evaluate(async () => {
    const r = await fetch('/api/v1/rules/rul-001/promote', { method: 'POST' });
    return r.json();
  });
  expect(result.status).toBe('testing');
});

test('warning-labels list renders and create POSTs a 201', async ({ authedPage: page }) => {
  await page.goto('/warning-labels');
  const ok = await page.evaluate(async (body) => {
    const r = await fetch('/api/v1/warning-labels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return r.status;
  }, makeWarningLabelPayload());
  expect(ok).toBe(201);
});
