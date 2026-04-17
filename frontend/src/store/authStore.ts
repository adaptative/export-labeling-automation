import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { User, Role } from '../lib/types';

const API_BASE = '/api/v1';

interface AuthUser {
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  tenant_id: string;
}

interface AuthState {
  user: User | null;
  role: Role | null;
  isAuthenticated: boolean;
  isSessionChecked: boolean;
  accessToken: string | null;
  expiresAt: number | null;
  isLoading: boolean;
  error: string | null;
  setUser: (user: User) => void;
  loginUser: (email: string, password: string) => Promise<void>;
  refreshAccessToken: () => Promise<void>;
  logout: () => Promise<void>;
  verifySession: () => Promise<void>;
}

function mapBackendRole(backendRole: string): Role {
  const roleMap: Record<string, Role> = {
    'ADMIN': 'Admin',
    'OPS': 'Merchandiser',
    'COMPLIANCE': 'Compliance Lead',
    'EXTERNAL': 'Importer QA',
  };
  return roleMap[backendRole] || 'Admin';
}

function mapAuthUserToUser(authUser: AuthUser): User {
  return {
    id: authUser.user_id,
    name: authUser.display_name,
    email: authUser.email,
    role: mapBackendRole(authUser.role),
    status: 'active',
    lastActive: new Date().toISOString(),
    mfaEnabled: false,
  };
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
  user: null,
  role: null,
  isAuthenticated: false,
  isSessionChecked: false,
  accessToken: null,
  expiresAt: null,
  isLoading: false,
  error: null,

  setUser: (user) => set({ user, role: user.role, isAuthenticated: true }),

  loginUser: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const resp = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(data.detail || 'Invalid credentials');
      }

      const data = await resp.json();
      const user = mapAuthUserToUser(data.user);

      set({
        user,
        role: user.role,
        isAuthenticated: true,
        accessToken: data.access_token,
        expiresAt: Date.now() + data.expires_in * 1000,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      set({ isLoading: false, error: err.message || 'Login failed' });
      throw err;
    }
  },

  refreshAccessToken: async () => {
    try {
      // The backend /auth/refresh endpoint identifies the caller via the
      // Bearer token (even when recently expired, once the server allows it).
      // Without this header the endpoint always 401s with "Missing or invalid
      // Authorization header" — which silently logs the user out mid-session.
      const { accessToken } = get();
      const headers: Record<string, string> = {};
      if (accessToken) {
        headers['Authorization'] = `Bearer ${accessToken}`;
      }

      const resp = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers,
      });

      if (!resp.ok) {
        // Refresh failed — force logout
        get().logout();
        return;
      }

      const data = await resp.json();
      set({
        accessToken: data.access_token,
        expiresAt: Date.now() + data.expires_in * 1000,
      });
    } catch {
      get().logout();
    }
  },

  logout: async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      });
    } catch {
      // Ignore network errors on logout
    }
    set({
      user: null,
      role: null,
      isAuthenticated: false,
      accessToken: null,
      expiresAt: null,
      error: null,
    });
  },

  verifySession: async () => {
    const { accessToken, expiresAt } = get();

    // If we have a valid token, check if it's expired
    if (accessToken && expiresAt && expiresAt > Date.now()) {
      set({ isSessionChecked: true });
      return; // Token still valid
    }

    // Try to refresh
    try {
      const resp = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!resp.ok) {
        set({ isAuthenticated: false, user: null, role: null, accessToken: null, isSessionChecked: true });
        return;
      }

      const data = await resp.json();

      // Fetch user info
      const meResp = await fetch(`${API_BASE}/auth/me`, {
        headers: { Authorization: `Bearer ${data.access_token}` },
      });

      if (meResp.ok) {
        const meData = await meResp.json();
        const user = mapAuthUserToUser(meData);
        set({
          user,
          role: user.role,
          isAuthenticated: true,
          isSessionChecked: true,
          accessToken: data.access_token,
          expiresAt: Date.now() + data.expires_in * 1000,
        });
      } else {
        set({ isSessionChecked: true });
      }
    } catch {
      set({ isAuthenticated: false, user: null, role: null, accessToken: null, isSessionChecked: true });
    }
  },
}),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        user: state.user,
        role: state.role,
        isAuthenticated: state.isAuthenticated,
        accessToken: state.accessToken,
        expiresAt: state.expiresAt,
      }),
    },
  ),
);
