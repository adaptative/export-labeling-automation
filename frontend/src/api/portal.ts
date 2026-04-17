/**
 * Client for external portal endpoints (INT-017, Sprint-13).
 *
 * Portal URLs are unauthenticated (no JWT) — they use an opaque bearer
 * token baked into the URL path. Calls bypass `authFetch` because the
 * auth store has no session on the portal pages.
 *
 * The backend returns:
 *   * 404 — invalid / wrong-role token
 *   * 409 — terminal action already taken (status != active)
 *   * 410 — token expired
 *   * 422 — invalid payload (e.g. empty reject reason)
 */

const API_BASE = '/api/v1';

export interface PortalOrderInfo {
  id: string;
  po_number: string | null;
  external_ref: string | null;
  importer_id: string | null;
  item_count: number;
}

export interface PortalImporterInfo {
  id: string | null;
  name: string | null;
  code: string | null;
}

export interface PortalItem {
  id: string;
  item_no: string;
  state: string;
  state_changed_at: string | null;
}

export interface PortalSessionResponse {
  role: 'importer' | 'printer';
  status: 'active' | 'approved' | 'rejected' | 'confirmed' | string;
  order: PortalOrderInfo;
  importer: PortalImporterInfo;
  items: PortalItem[];
  expires_at: string | null;
  action_taken_at: string | null;
}

export interface PortalActionResponse {
  ok: boolean;
  status: string;
  order_id: string;
  action_taken_at: string;
  message: string;
}

export interface PortalApproveRequest {
  approver_name?: string;
  approver_email?: string;
  note?: string;
}

export interface PortalRejectRequest {
  reason: string;
  reviewer_name?: string;
  reviewer_email?: string;
}

export interface PortalPrinterConfirmRequest {
  printer_name?: string;
  printer_email?: string;
  note?: string;
}

/** Error with an HTTP status code for UI-side branching (409 duplicate, 410 expired, etc). */
export class PortalApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function portalFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, init);
  let body: unknown;
  try {
    body = await resp.json();
  } catch {
    body = null;
  }
  if (!resp.ok) {
    const message =
      (body && typeof body === 'object' && 'detail' in (body as Record<string, unknown>)
        ? String((body as Record<string, unknown>).detail)
        : `Portal error ${resp.status}`);
    throw new PortalApiError(resp.status, message, body);
  }
  return body as T;
}

// ── Importer flow ────────────────────────────────────────────────────────

export function getImporterSession(token: string): Promise<PortalSessionResponse> {
  return portalFetch<PortalSessionResponse>(`/portal/importer/${encodeURIComponent(token)}`);
}

export function approveImporter(
  token: string,
  body: PortalApproveRequest = {},
): Promise<PortalActionResponse> {
  return portalFetch<PortalActionResponse>(
    `/portal/importer/${encodeURIComponent(token)}/approve`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

export function rejectImporter(
  token: string,
  body: PortalRejectRequest,
): Promise<PortalActionResponse> {
  return portalFetch<PortalActionResponse>(
    `/portal/importer/${encodeURIComponent(token)}/reject`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

// ── Printer flow ─────────────────────────────────────────────────────────

export function getPrinterSession(token: string): Promise<PortalSessionResponse> {
  return portalFetch<PortalSessionResponse>(`/portal/printer/${encodeURIComponent(token)}`);
}

export function confirmPrinter(
  token: string,
  body: PortalPrinterConfirmRequest = {},
): Promise<PortalActionResponse> {
  return portalFetch<PortalActionResponse>(
    `/portal/printer/${encodeURIComponent(token)}/confirm`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
  );
}

// ── Token-scoped bundle download ─────────────────────────────────────────

export type ArtifactMissingReason = 'not_generated' | 'blob_missing';

export interface PortalArtifactMissing {
  kind: 'missing';
  reason: ArtifactMissingReason;
  detail?: string;
}

export interface PortalArtifactBlob {
  kind: 'blob';
  /** Object URL — caller is responsible for `URL.revokeObjectURL(url)`. */
  url: string;
  mime: string;
  bytes: Blob;
}

export type PortalArtifactResult = PortalArtifactBlob | PortalArtifactMissing;

/**
 * Download a printer bundle for a single item, authed by the portal token.
 * Uses the unauthenticated `/portal/printer/{token}/items/{item_id}/bundle`
 * route — see `portal.py::get_printer_item_bundle`.
 */
export async function getPrinterItemBundle(
  token: string,
  itemId: string,
): Promise<PortalArtifactResult> {
  const resp = await fetch(
    `${API_BASE}/portal/printer/${encodeURIComponent(token)}/items/${encodeURIComponent(itemId)}/bundle`,
  );
  if (resp.status === 404 || resp.status === 410) {
    try {
      const body = await resp.json();
      if (body && typeof body === 'object' && 'reason' in body) {
        return {
          kind: 'missing',
          reason: body.reason as ArtifactMissingReason,
          detail: (body as Record<string, unknown>).detail as string | undefined,
        };
      }
    } catch {
      // fall through
    }
    return { kind: 'missing', reason: 'not_generated' };
  }
  if (!resp.ok) {
    throw new PortalApiError(resp.status, `Bundle download failed: ${resp.status}`);
  }
  const bytes = await resp.blob();
  const mime = resp.headers.get('content-type') || 'application/zip';
  return { kind: 'blob', url: URL.createObjectURL(bytes), mime, bytes };
}
