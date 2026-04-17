/**
 * API route mocks for Playwright (INT-024 · Sprint-17).
 *
 * Playwright intercepts outbound ``/api/v1/*`` requests and replies with
 * deterministic payloads, so the specs can exercise the full React-Query
 * + routing stack without depending on a live backend. Swap
 * ``PLAYWRIGHT_TEST_URL`` + ``PLAYWRIGHT_LIVE_BACKEND=1`` to skip the
 * mocks and drive a real Docker Compose stack instead.
 */
import type { Page, Route, Request } from '@playwright/test';

const USE_LIVE = process.env.PLAYWRIGHT_LIVE_BACKEND === '1';

export interface MockOrder {
  id: string;
  importer_id: string;
  po_number: string;
  state: string;
  item_count: number;
  created_at: string;
  updated_at: string;
}

export function buildOrder(i: number): MockOrder {
  const id = `ord-e2e-${String(i).padStart(3, '0')}`;
  return {
    id,
    importer_id: i % 2 ? 'IMP-ACME' : 'IMP-BETA',
    po_number: `PO-E2E-${String(i).padStart(4, '0')}`,
    state: ['draft', 'extracting', 'ready', 'printed'][i % 4],
    item_count: 3 + (i % 7),
    created_at: new Date(Date.now() - i * 86_400_000).toISOString(),
    updated_at: new Date(Date.now() - i * 3_600_000).toISOString(),
  };
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

function matchPath(url: string, suffix: string) {
  // Pathname-equality (with optional query) rather than substring —
  // prevents ``/documents/doc-001/status`` from matching ``/documents``.
  const pathname = new URL(url).pathname;
  return pathname === `/api/v1${suffix}`;
}

/**
 * Register a default set of mocks on a page. Tests can override specific
 * routes afterwards with ``page.route(...)`` to simulate errors or
 * custom payloads.
 */
export async function installDefaultMocks(page: Page): Promise<void> {
  if (USE_LIVE) return;

  await page.route('**/api/v1/**', async (route: Route, req: Request) => {
    const url = req.url();
    const method = req.method();

    // ── Auth ────────────────────────────────────────────────────────────
    if (matchPath(url, '/auth/me') && method === 'GET') {
      return json(route, {
        id: 'usr-admin-001',
        email: 'admin@nakodacraft.com',
        display_name: 'Admin Nakoda',
        tenant_id: 'tnt-nakoda-001',
        role: 'ADMIN',
      });
    }
    if (matchPath(url, '/auth/login') && method === 'POST') {
      const body = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
      if (body.email === 'bad@example.com') {
        return json(route, { detail: 'Invalid credentials' }, 401);
      }
      return json(route, {
        access_token: 'stub.jwt.token',
        expires_in: 3600,
        user: {
          id: 'usr-admin-001',
          email: body.email ?? 'admin@nakodacraft.com',
          display_name: 'Admin Nakoda',
          tenant_id: 'tnt-nakoda-001',
          role: 'ADMIN',
        },
      });
    }
    if (matchPath(url, '/auth/refresh') && method === 'POST') {
      return json(route, {
        access_token: 'stub.jwt.refreshed',
        expires_in: 3600,
        user: {
          id: 'usr-admin-001',
          email: 'admin@nakodacraft.com',
          display_name: 'Admin Nakoda',
          tenant_id: 'tnt-nakoda-001',
          role: 'ADMIN',
        },
      });
    }
    if (matchPath(url, '/auth/logout') && method === 'POST') {
      return json(route, { ok: true });
    }

    // ── Orders ──────────────────────────────────────────────────────────
    if (matchPath(url, '/orders') && method === 'GET') {
      const orders = Array.from({ length: 24 }, (_, i) => buildOrder(i));
      return json(route, { orders, total: orders.length });
    }
    if (matchPath(url, '/orders') && method === 'POST') {
      const body = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
      return json(
        route,
        {
          ...buildOrder(999),
          id: `ord-e2e-new-${Date.now()}`,
          po_number: body.po_reference ?? 'PO-E2E-NEW',
          importer_id: body.importer_id ?? 'IMP-ACME',
          state: 'draft',
          item_count: 0,
        },
        201,
      );
    }
    if (/\/orders\/ord-[a-z0-9-]+$/.test(new URL(url).pathname) && method === 'GET') {
      const id = new URL(url).pathname.split('/').pop()!;
      return json(route, {
        ...buildOrder(1),
        id,
        items: [
          {
            id: `itm-${id}-1`,
            item_no: 'ITM-001',
            state: 'ready',
            data: { description: 'Scented candle', upc: '0123456', case_qty: '12' },
          },
        ],
      });
    }
    if (/\/orders\/[^/]+\/approve$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, state: 'approved' });
    }
    if (/\/orders\/[^/]+\/reject$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, state: 'rejected' });
    }
    if (/\/orders\/[^/]+\/send-to-printer$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, state: 'sent_to_printer' });
    }

    // ── Importers ───────────────────────────────────────────────────────
    if (matchPath(url, '/importers') && method === 'GET') {
      return json(route, {
        importers: [
          { id: 'IMP-ACME', name: 'Acme Imports', country: 'US', onboarded: true },
          { id: 'IMP-BETA', name: 'Beta Traders', country: 'DE', onboarded: true },
        ],
        total: 2,
      });
    }
    if (matchPath(url, '/importers') && method === 'POST') {
      const body = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
      return json(
        route,
        {
          id: `IMP-E2E-${Date.now()}`,
          name: body.name ?? 'E2E importer',
          country: body.country ?? 'US',
          onboarded: false,
        },
        201,
      );
    }
    if (/\/importers\/[^/]+\/onboard\/finalize$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, onboarded: true });
    }
    if (/\/importers\/[^/]+\/onboard\/extract-status$/.test(new URL(url).pathname)) {
      return json(route, { status: 'completed', progress: 100 });
    }

    // ── HiTL ────────────────────────────────────────────────────────────
    if (matchPath(url, '/hitl/threads') && method === 'GET') {
      return json(route, {
        threads: [
          {
            id: 'thr-001',
            subject: 'Please confirm country of origin',
            state: 'open',
            created_at: new Date().toISOString(),
            last_message_at: new Date().toISOString(),
            unread_count: 2,
          },
        ],
        total: 1,
      });
    }
    if (/\/hitl\/threads\/[^/]+\/messages$/.test(new URL(url).pathname) && method === 'GET') {
      return json(route, {
        messages: [
          {
            id: 'msg-001',
            thread_id: 'thr-001',
            author: 'system',
            body: 'Is this product bound for California?',
            options: ['Yes', 'No', 'Unsure'],
            created_at: new Date().toISOString(),
          },
        ],
      });
    }
    if (/\/hitl\/threads\/[^/]+\/messages$/.test(new URL(url).pathname) && method === 'POST') {
      const body = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
      return json(route, {
        id: `msg-${Date.now()}`,
        thread_id: 'thr-001',
        author: 'human',
        body: body.body ?? '',
        created_at: new Date().toISOString(),
      }, 201);
    }
    if (/\/hitl\/threads\/[^/]+\/option-select$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true });
    }
    if (/\/hitl\/threads\/[^/]+\/resolve$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, state: 'resolved' });
    }

    // ── Rules / warning labels ──────────────────────────────────────────
    if (matchPath(url, '/rules') && method === 'GET') {
      return json(route, {
        rules: [
          {
            id: 'rul-001',
            name: 'Case qty must be positive',
            status: 'active',
            severity: 'error',
            dsl: 'item.case_qty > 0',
          },
        ],
        total: 1,
      });
    }
    if (matchPath(url, '/rules') && method === 'POST') {
      const body = ((() => { try { return req.postDataJSON() ?? {}; } catch { return {}; } })());
      return json(
        route,
        {
          id: `rul-${Date.now()}`,
          name: body.name ?? 'Rule',
          status: 'draft',
          severity: body.severity ?? 'warn',
          dsl: body.dsl ?? '',
        },
        201,
      );
    }
    if (/\/rules\/[^/]+$/.test(new URL(url).pathname) && method === 'PUT') {
      return json(route, { ok: true });
    }
    if (/\/rules\/[^/]+\/dry-run$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, {
        newly_failing: 3,
        newly_passing: 1,
        unchanged: 42,
        sample_failures: [{ item_id: 'itm-001', reason: 'case_qty <= 0' }],
      });
    }
    if (/\/rules\/[^/]+\/promote$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, status: 'testing' });
    }
    if (matchPath(url, '/warning-labels') && method === 'GET') {
      return json(route, {
        labels: [{ id: 'wl-001', sku: 'SKU-001', product_name: 'Candle', country: 'US' }],
        total: 1,
      });
    }
    if (matchPath(url, '/warning-labels') && method === 'POST') {
      return json(route, { id: `wl-${Date.now()}`, ok: true }, 201);
    }

    // ── Documents ───────────────────────────────────────────────────────
    if (matchPath(url, '/documents') && method === 'GET') {
      return json(route, {
        documents: [
          {
            id: 'doc-001',
            filename: 'po-specimen.pdf',
            classification: 'purchase_order',
            confidence: 0.94,
            state: 'classified',
            uploaded_at: new Date().toISOString(),
          },
        ],
        total: 1,
      });
    }
    if (matchPath(url, '/documents') && method === 'POST') {
      return json(route, { id: `doc-${Date.now()}`, state: 'uploaded' }, 201);
    }
    if (/\/documents\/[^/]+\/classify$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true, classification: 'purchase_order', confidence: 0.98 });
    }
    if (/\/documents\/[^/]+\/status$/.test(new URL(url).pathname) && method === 'GET') {
      return json(route, { status: 'classified', confidence: 0.94 });
    }

    // ── Cost ────────────────────────────────────────────────────────────
    if (matchPath(url, '/cost/overview') && method === 'GET') {
      return json(route, {
        tiers: [
          { name: 'Monthly budget', used: 420, cap: 1000 },
          { name: 'Daily burn', used: 32, cap: 75 },
          { name: 'Per-agent cap', used: 8.3, cap: 25 },
          { name: 'HiTL routing', used: 2.1, cap: 5 },
        ],
        breakers: [{ name: 'daily', breached: false }],
      });
    }
    if (matchPath(url, '/budgets/tenant') && method === 'PUT') {
      return json(route, { ok: true });
    }

    // ── Audit ───────────────────────────────────────────────────────────
    if (matchPath(url, '/audit') && method === 'GET') {
      const uri = new URL(url);
      const actorType = uri.searchParams.get('actor_type');
      const action = uri.searchParams.get('action');
      const events = [
        {
          id: 'aud-001',
          actor_type: 'user',
          actor_id: 'usr-admin-001',
          action: 'order.create',
          target_id: 'ord-001',
          created_at: new Date().toISOString(),
        },
        {
          id: 'aud-002',
          actor_type: 'agent',
          actor_id: 'intake-classifier',
          action: 'document.classify',
          target_id: 'doc-001',
          created_at: new Date().toISOString(),
        },
      ].filter(
        (e) =>
          (!actorType || e.actor_type === actorType) &&
          (!action || e.action === action),
      );
      return json(route, { events, total: events.length });
    }

    // ── Agents / evals / analytics (Sprint-16) ─────────────────────────
    if (matchPath(url, '/agents') && method === 'GET') {
      return json(route, {
        agents: [
          {
            agent_id: 'intake-classifier',
            name: 'Intake Classifier',
            kind: 'intake',
            status: 'healthy',
            calls: 120,
            successes: 118,
            failures: 2,
            success_rate: 0.983,
            avg_latency_ms: 412,
            total_cost_usd: 1.23,
            last_call_at: Math.floor(Date.now() / 1000) - 120,
          },
        ],
        total: 1,
      });
    }
    if (matchPath(url, '/evals') && method === 'GET') {
      return json(route, {
        evals: [
          {
            id: 'ev-001',
            agent_id: 'intake-classifier',
            agent_name: 'Intake Classifier',
            batch_id: null,
            eval_date: Math.floor(Date.now() / 1000),
            status: 'pass',
            metrics: {
              precision: 0.97,
              recall: 0.95,
              f1_score: 0.96,
              accuracy: 0.94,
              cost_delta: -1.2,
              sample_size: 200,
            },
          },
        ],
        total: 1,
      });
    }
    if (matchPath(url, '/evals/run-all') && method === 'POST') {
      return json(route, {
        eval_batch_id: 'batch-e2e',
        status: 'queued',
        started_at: Math.floor(Date.now() / 1000),
      });
    }
    if (matchPath(url, '/evals/run-all/batch-e2e') && method === 'GET') {
      return json(route, {
        eval_batch_id: 'batch-e2e',
        status: 'completed',
        total: 1,
        completed: 1,
        failed: 0,
        started_at: Math.floor(Date.now() / 1000) - 2,
        finished_at: Math.floor(Date.now() / 1000),
        results: [],
      });
    }
    if (matchPath(url, '/analytics/automation-rate')) {
      const today = new Date();
      const points = Array.from({ length: 30 }, (_, i) => {
        const d = new Date(today);
        d.setDate(d.getDate() - (29 - i));
        return {
          date: d.toISOString().slice(0, 10),
          rate_percent: 72 + (i % 5),
          intake_errors: i % 3,
          fusion_errors: i % 4,
          compliance_errors: i % 2,
        };
      });
      return json(route, {
        points,
        summary: {
          current_rate: 74.2,
          average_rate: 72.8,
          target_low: 60,
          target_high: 85,
          best_day: points[points.length - 3],
          worst_day: points[4],
          trend_pct: 2.1,
          top_error_stage: 'fusion',
        },
      });
    }

    // ── Portal ──────────────────────────────────────────────────────────
    if (/\/portal\/importer\/[^/]+$/.test(new URL(url).pathname) && method === 'GET') {
      return json(route, {
        order: { id: 'ord-portal', po_number: 'PO-PORTAL-1', state: 'awaiting_approval' },
        protocol: { id: 'prot-001', version: '1.0', checksum: 'abc123' },
      });
    }
    if (/\/portal\/importer\/[^/]+\/approve$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true });
    }
    if (/\/portal\/printer\/[^/]+$/.test(new URL(url).pathname) && method === 'GET') {
      return json(route, {
        print_job: { id: 'pj-001', state: 'ready', labels: [{ id: 'lbl-001', sku: 'SKU-001' }] },
      });
    }
    if (/\/portal\/printer\/[^/]+\/labels\/[^/]+\/pdf$/.test(new URL(url).pathname)) {
      return route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        body: Buffer.from('%PDF-1.4\n%stub\n'),
      });
    }
    if (/\/portal\/printer\/[^/]+\/confirm$/.test(new URL(url).pathname) && method === 'POST') {
      return json(route, { ok: true });
    }

    // Default: pass through empty list so pages do not crash
    if (method === 'GET') return json(route, { items: [], total: 0 });
    if (method === 'POST' || method === 'PUT') return json(route, { ok: true });

    return route.continue();
  });
}
