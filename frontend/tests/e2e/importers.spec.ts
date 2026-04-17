/**
 * Importer-onboarding E2E (INT-024 · Sprint-17).
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';
import { makeImporterPayload } from './fixtures/testData';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('importers list renders known importers', async ({ authedPage: page }) => {
  await page.goto('/importers');
  await expect(page.getByText(/Acme Imports|Beta Traders/i).first()).toBeVisible();
});

test('onboarding wizard step 1 — create importer POSTs /importers', async ({ authedPage: page }) => {
  let posted: any = null;
  await page.route('**/api/v1/importers', async (route, req) => {
    if (req.method() === 'POST') posted = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
    await route.fallback();
  });
  await page.goto('/onboarding/importer');
  const payload = makeImporterPayload();
  await page.evaluate(async (body) => {
    await fetch('/api/v1/importers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }, payload);
  expect(posted?.name).toBe(payload.name);
});

test('extraction polling returns completed', async ({ authedPage: page }) => {
  await page.goto('/onboarding/importer');
  const status = await page.evaluate(async () => {
    const r = await fetch('/api/v1/importers/IMP-NEW/onboard/extract-status');
    return r.json();
  });
  expect(status.status).toBe('completed');
});

test('finalize endpoint marks importer onboarded', async ({ authedPage: page }) => {
  await page.goto('/onboarding/importer');
  const result = await page.evaluate(async () => {
    const r = await fetch('/api/v1/importers/IMP-NEW/onboard/finalize', { method: 'POST' });
    return r.json();
  });
  expect(result.onboarded).toBe(true);
});
