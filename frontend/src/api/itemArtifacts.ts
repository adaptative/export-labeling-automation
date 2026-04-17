import { apiGet, authFetch } from './authInterceptor';

/**
 * Client for per-item artifact endpoints (INT-006, Sprint-13).
 *
 * Binary artifacts (die-cut SVG, approval PDF, line drawing, bundle ZIP)
 * live at URLs that the UI can either fetch as bytes (to inline SVG) or
 * embed directly via `<iframe>` / `<a download>`. The backend returns
 * structured 404s with `{reason: "not_generated" | "blob_missing"}` when
 * the artifact row or underlying blob is missing — callers get a
 * discriminated union so the UI can render a friendly empty state.
 */

const API_BASE = '/api/v1';

export interface OrderItemSummary {
  id: string;
  order_id: string;
  item_no: string;
  state: string;
  state_changed_at: string;
  rules_snapshot_id: string | null;
}

export interface ItemHistoryEntry {
  step: number;
  at: string;
  actor: string | null;
  actor_type: string;
  action: string;
  from_state: string | null;
  to_state: string | null;
  detail: string | null;
}

export interface ItemHistoryResponse {
  item_id: string;
  item_no: string;
  current_state: string;
  events: ItemHistoryEntry[];
}

export type ArtifactMissingReason = 'not_generated' | 'blob_missing';

export interface ArtifactMissing {
  kind: 'missing';
  reason: ArtifactMissingReason;
  detail?: string;
}

export interface ArtifactBlob {
  kind: 'blob';
  /** Object URL — caller is responsible for `URL.revokeObjectURL(url)`. */
  url: string;
  mime: string;
  bytes: Blob;
  contentHash?: string;
}

export type ArtifactResult = ArtifactBlob | ArtifactMissing;

// ── Read helpers ──────────────────────────────────────────────────────────

export async function getItem(itemId: string): Promise<OrderItemSummary> {
  return apiGet<OrderItemSummary>(`/items/${encodeURIComponent(itemId)}`);
}

export async function getItemHistory(itemId: string): Promise<ItemHistoryResponse> {
  return apiGet<ItemHistoryResponse>(`/items/${encodeURIComponent(itemId)}/history`);
}

/**
 * Fetch a binary artifact as an object URL, or resolve to `{kind: 'missing'}`
 * when the backend returns a structured 404.
 */
async function fetchArtifact(
  path: string, defaultMime: string,
): Promise<ArtifactResult> {
  const resp = await authFetch(`${API_BASE}${path}`);

  if (resp.status === 404) {
    try {
      const body = await resp.json();
      if (body && typeof body === 'object' && body.reason) {
        return {
          kind: 'missing',
          reason: body.reason as ArtifactMissingReason,
          detail: body.detail,
        };
      }
    } catch {
      // Non-JSON 404 — fall through.
    }
    return { kind: 'missing', reason: 'not_generated' };
  }

  if (!resp.ok) {
    throw new Error(`Artifact fetch failed: ${resp.status}`);
  }

  const bytes = await resp.blob();
  const mime = resp.headers.get('content-type') || defaultMime;
  const contentHash = resp.headers.get('x-content-hash') || undefined;
  const url = URL.createObjectURL(bytes);
  return { kind: 'blob', url, mime, bytes, contentHash };
}

export function getDiecutSvg(itemId: string): Promise<ArtifactResult> {
  return fetchArtifact(`/items/${encodeURIComponent(itemId)}/diecut-svg`, 'image/svg+xml');
}

export function getApprovalPdf(itemId: string): Promise<ArtifactResult> {
  return fetchArtifact(`/items/${encodeURIComponent(itemId)}/approval-pdf`, 'application/pdf');
}

export function getLineDrawing(itemId: string): Promise<ArtifactResult> {
  return fetchArtifact(`/items/${encodeURIComponent(itemId)}/line-drawing`, 'image/svg+xml');
}

export function getBundle(itemId: string): Promise<ArtifactResult> {
  return fetchArtifact(`/items/${encodeURIComponent(itemId)}/bundle`, 'application/zip');
}
