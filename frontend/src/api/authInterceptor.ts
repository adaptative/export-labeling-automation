import { useAuthStore } from '../store/authStore';

const API_BASE = '/api/v1';

/**
 * Authenticated fetch wrapper that:
 * 1. Adds Authorization header with access token
 * 2. Intercepts 401 responses and auto-refreshes token
 * 3. On second 401, forces logout to /login
 */
export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit
): Promise<Response> {
  const { accessToken, refreshAccessToken, logout } = useAuthStore.getState();

  const headers = new Headers(init?.headers);
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  let response = await fetch(input, { ...init, headers });

  if (response.status === 401) {
    // Try to refresh token
    await refreshAccessToken();

    const newToken = useAuthStore.getState().accessToken;
    if (newToken) {
      headers.set('Authorization', `Bearer ${newToken}`);
      response = await fetch(input, { ...init, headers });

      if (response.status === 401) {
        // Second 401 — force logout
        await logout();
        window.location.href = '/login';
      }
    } else {
      // Refresh failed
      await logout();
      window.location.href = '/login';
    }
  }

  return response;
}

/**
 * Convenience wrapper for JSON API calls.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'POST',
    body: formData,
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  return resp.json();
}

export async function apiDelete<T = void>(path: string): Promise<T> {
  const resp = await authFetch(`${API_BASE}${path}`, {
    method: 'DELETE',
  });
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status}`);
  }
  // Some DELETE endpoints return 204 No Content
  if (resp.status === 204) return undefined as T;
  return resp.json();
}
