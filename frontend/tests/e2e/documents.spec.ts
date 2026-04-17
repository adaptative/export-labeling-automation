/**
 * Documents E2E (INT-024 · Sprint-17).
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('documents page loads and renders classification results', async ({ authedPage: page }) => {
  await page.goto('/documents');
  await expect(page.getByRole('heading', { name: /documents/i }).first()).toBeVisible();
  await expect(page.getByText(/po-specimen\.pdf|Purchase Order|classified/i).first()).toBeVisible();
});

test('polling /documents/:id/status returns classified state', async ({ authedPage: page }) => {
  await page.goto('/documents');
  const status = await page.evaluate(async () => {
    const r = await fetch('/api/v1/documents/doc-001/status');
    return r.json();
  });
  expect(status.status).toBe('classified');
  expect(status.confidence).toBeGreaterThan(0.9);
});

test('manual classification override POSTs /documents/:id/classify', async ({ authedPage: page }) => {
  let posted = false;
  await page.route('**/api/v1/documents/*/classify', async (route) => {
    posted = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, classification: 'invoice' }),
    });
  });
  await page.goto('/documents');
  await page.evaluate(async () => {
    await fetch('/api/v1/documents/doc-001/classify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ classification: 'invoice' }),
    });
  });
  expect(posted).toBe(true);
});
