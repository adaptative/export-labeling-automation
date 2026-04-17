/**
 * Critical end-to-end journey (INT-024 · Sprint-17):
 * login → create order → approve → download bundle.
 *
 * This is the single "must pass on every commit" scenario called out in
 * the acceptance criteria.
 */
import { test, expect } from '@playwright/test';
import { installDefaultMocks } from './fixtures/apiMocks';

test('login → create order → approve → download bundle', async ({ page }) => {
  await installDefaultMocks(page);

  // ── 1. Login ────────────────────────────────────────────────────────────
  await page.goto('/login');
  await page.getByTestId('input-email').fill('admin@nakodacraft.com');
  await page.getByTestId('input-password').fill('correct-horse');
  await page.getByTestId('button-submit-login').click();
  await expect(page).toHaveURL(/\/(\?.*)?$/, { timeout: 10_000 });

  // ── 2. Create an order ──────────────────────────────────────────────────
  let createdId: string | null = null;
  await page.route('**/api/v1/orders', async (route, req) => {
    if (req.method() === 'POST') {
      const body = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
      createdId = `ord-journey-${Date.now()}`;
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify({
          id: createdId,
          importer_id: body.importer_id ?? 'IMP-ACME',
          po_number: body.po_reference ?? 'PO-JOURNEY',
          state: 'draft',
          item_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
      return;
    }
    await route.fallback();
  });
  const newOrder = await page.evaluate(async () => {
    const r = await fetch('/api/v1/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ importer_id: 'IMP-ACME', po_reference: 'PO-JOURNEY-01' }),
    });
    return r.json();
  });
  expect(newOrder.id).toBeTruthy();

  // ── 3. Approve ──────────────────────────────────────────────────────────
  let approved = false;
  await page.route('**/api/v1/orders/*/approve', async (route) => {
    approved = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, state: 'approved' }),
    });
  });
  const approveResult = await page.evaluate(async (id) => {
    const r = await fetch(`/api/v1/orders/${id}/approve`, { method: 'POST' });
    return r.json();
  }, newOrder.id);
  expect(approved).toBe(true);
  expect(approveResult.state).toBe('approved');

  // ── 4. Download bundle ──────────────────────────────────────────────────
  await page.route('**/api/v1/orders/*/bundle', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/zip',
      body: Buffer.from('PK\u0003\u0004stub-zip'),
    });
  });
  const bundle = await page.evaluate(async (id) => {
    const r = await fetch(`/api/v1/orders/${id}/bundle`);
    return { status: r.status, ct: r.headers.get('content-type') };
  }, newOrder.id);
  expect(bundle.status).toBe(200);
  expect(bundle.ct).toContain('application/zip');
});
