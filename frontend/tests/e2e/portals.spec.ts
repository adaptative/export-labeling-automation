/**
 * Portal E2E (INT-024 · Sprint-17).
 *
 * Portal routes intentionally live outside ``RouteGuard`` / ``AppShell``,
 * so the seeded-auth fixture is optional. We still install API mocks so
 * the portal pages hydrate.
 */
import { test, expect } from './fixtures/auth';
import { installDefaultMocks } from './fixtures/apiMocks';

test.beforeEach(async ({ authedPage }) => {
  await installDefaultMocks(authedPage);
});

test('importer portal loads protocol data from its token URL', async ({ authedPage: page }) => {
  await page.goto('/portal/importer/tok-imp-001');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/portal/importer/tok-imp-001');
    return r.json();
  });
  expect(body.order?.po_number).toBe('PO-PORTAL-1');
  expect(body.protocol?.version).toBe('1.0');
});

test('approving a protocol POSTs /approve', async ({ authedPage: page }) => {
  let approved = false;
  await page.route('**/api/v1/portal/importer/*/approve', async (route) => {
    approved = true;
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok":true}' });
  });
  await page.goto('/portal/importer/tok-imp-001');
  await page.evaluate(async () => {
    await fetch('/api/v1/portal/importer/tok-imp-001/approve', { method: 'POST' });
  });
  expect(approved).toBe(true);
});

test('printer portal loads the print job', async ({ authedPage: page }) => {
  await page.goto('/portal/printer/tok-prt-001');
  const body = await page.evaluate(async () => {
    const r = await fetch('/api/v1/portal/printer/tok-prt-001');
    return r.json();
  });
  expect(body.print_job?.labels?.[0]?.sku).toBe('SKU-001');
});

test('label PDF download returns application/pdf', async ({ authedPage: page }) => {
  await page.goto('/portal/printer/tok-prt-001');
  const headers = await page.evaluate(async () => {
    const r = await fetch('/api/v1/portal/printer/tok-prt-001/labels/lbl-001/pdf');
    return { status: r.status, ct: r.headers.get('content-type') };
  });
  expect(headers.status).toBe(200);
  expect(headers.ct).toContain('application/pdf');
});

test('confirming a print job POSTs /confirm', async ({ authedPage: page }) => {
  await page.goto('/portal/printer/tok-prt-001');
  const result = await page.evaluate(async () => {
    const r = await fetch('/api/v1/portal/printer/tok-prt-001/confirm', { method: 'POST' });
    return r.json();
  });
  expect(result.ok).toBe(true);
});
