/**
 * Authentication Module for Cauveris Frontend
 * Handles JWT token management, user sessions, and authentication state
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { CauverisError, handleApiError } from './api';

// Types
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: string;
  org_id: string;
  is_active: boolean;
  mfa_enabled: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface LoginRequest {
  email: string;
  password: string;
  remember_me?: boolean;
  mfa_code?: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  org_name?: string;
  org_slug?: string;
}

export type AuthStatus = 'CHECKING' | 'AUTHENTICATED' | 'UNAUTHENTICATED' | 'ERROR';

export interface AuthState {
  // Token storage
  accessToken: string | null;
  refreshToken: string | null;
  tokenExpiry: number | null; // Unix timestamp

  // User state
  user: User | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshAccessToken: () => Promise<boolean>;
  initializeAuth: () => Promise<void>;
  clearError: () => void;
}

// Token storage key
const TOKEN_STORAGE_KEY = 'cauveris_auth_tokens';
const userStorageKey = 'cauveris_auth_user';

// Helper functions for token storage
function parseApiErrorMessage(errorData: any, fallback: string): string {
  if (!errorData) return fallback;
  if (typeof errorData === 'string') return errorData;
  if (typeof errorData.detail === 'string') return errorData.detail;
  if (Array.isArray(errorData.detail)) {
    return errorData.detail
      .map((d: any) => {
        if (typeof d === 'string') return d;
        if (d && typeof d === 'object') {
          return d.msg || d.message || JSON.stringify(d);
        }
        return String(d);
      })
      .filter(Boolean)
      .join(', ');
  }
  if (errorData.detail && typeof errorData.detail === 'object') {
    return errorData.detail.msg || errorData.detail.message || JSON.stringify(errorData.detail);
  }
  if (typeof errorData.error === 'string') return errorData.error;
  if (typeof errorData.message === 'string') return errorData.message;
  return fallback;
}

function storeTokens(accessToken: string, refreshToken: string, expiresIn: number) {
  if (typeof window !== 'undefined') {
    const expiry = Date.now() + expiresIn * 1000;
    localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify({
      accessToken,
      refreshToken,
      expiry,
    }));
    try {
      document.cookie = `access_token=${accessToken}; path=/; max-age=${expiresIn}; SameSite=Lax`;
    } catch {
      // Ignore cookie errors
    }
  }
}

function getStoredTokens(): { accessToken: string | null; refreshToken: string | null; expiry: number | null } {
  if (typeof window === 'undefined') {
    return { accessToken: null, refreshToken: null, expiry: null };
  }
  try {
    const stored = localStorage.getItem(TOKEN_STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        accessToken: parsed.accessToken,
        refreshToken: parsed.refreshToken,
        expiry: parsed.expiry,
      };
    }
  } catch {
    // Ignore parse errors
  }
  return { accessToken: null, refreshToken: null, expiry: null };
}

function clearTokens() {
  if (typeof window !== 'undefined') {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    localStorage.removeItem(userStorageKey);
    try {
      document.cookie = 'access_token=; path=/; max-age=0; SameSite=Lax';
    } catch {
      // Ignore
    }
  }
}

function storeUser(user: User) {
  if (typeof window !== 'undefined') {
    localStorage.setItem(userStorageKey, JSON.stringify(user));
  }
}

function getStoredUser(): User | null {
  if (typeof window === 'undefined') return null;
  try {
    const stored = localStorage.getItem(userStorageKey);
    if (stored) return JSON.parse(stored);
  } catch {
    // Ignore
  }
  return null;
}

// Single-flight promises
let refreshPromise: Promise<boolean> | null = null;
let initAuthPromise: Promise<void> | null = null;

// Check if token is expired (with 30 second buffer)
function isTokenExpired(expiry: number | null): boolean {
  if (!expiry) return true;
  return Date.now() >= (expiry - 30000); // 30 second buffer
}

// Create the auth store with Zustand + persistence
// Note: We only persist user info, not tokens (tokens in localStorage directly)
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      // Initial state
      accessToken: null,
      refreshToken: null,
      tokenExpiry: null,
      user: null,
      status: 'CHECKING',
      isAuthenticated: false,
      isLoading: true, // Start with true to prevent flash of unauthenticated content
      error: null,

      // Clear error
      clearError: () => set({ error: null }),

      // Initialize auth from persistent session and backend verification
      initializeAuth: async () => {
        if (initAuthPromise) {
          return initAuthPromise;
        }

        initAuthPromise = (async () => {
          set({ isLoading: true, status: 'CHECKING' });
          const { accessToken, refreshToken, expiry } = getStoredTokens();
          const apiBase = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000/api/v1';

          try {
            const headers: Record<string, string> = { 'Accept': 'application/json' };
            if (accessToken) {
              headers['Authorization'] = `Bearer ${accessToken}`;
            }

            const response = await fetch(`${apiBase}/auth/me`, {
              method: 'GET',
              headers,
              credentials: 'include',
            });

            if (response.ok) {
              const userData: User = await response.json();
              storeUser(userData);
              set({
                user: userData,
                accessToken: accessToken || getStoredTokens().accessToken,
                refreshToken: refreshToken || getStoredTokens().refreshToken,
                tokenExpiry: expiry,
                isAuthenticated: true,
                status: 'AUTHENTICATED',
                isLoading: false,
                error: null,
              });
              return;
            }

            if (response.status === 401 && refreshToken) {
              const refreshed = await get().refreshAccessToken();
              if (refreshed) {
                const newTokens = getStoredTokens();
                const retryRes = await fetch(`${apiBase}/auth/me`, {
                  method: 'GET',
                  headers: {
                    'Accept': 'application/json',
                    'Authorization': `Bearer ${newTokens.accessToken}`,
                  },
                  credentials: 'include',
                });
                if (retryRes.ok) {
                  const userData: User = await retryRes.json();
                  storeUser(userData);
                  set({
                    user: userData,
                    accessToken: newTokens.accessToken,
                    refreshToken: newTokens.refreshToken,
                    tokenExpiry: newTokens.expiry,
                    isAuthenticated: true,
                    status: 'AUTHENTICATED',
                    isLoading: false,
                    error: null,
                  });
                  return;
                }
              }
            }

            // Unauthenticated or revoked session
            clearTokens();
            set({
              user: null,
              accessToken: null,
              refreshToken: null,
              tokenExpiry: null,
              isAuthenticated: false,
              status: 'UNAUTHENTICATED',
              isLoading: false,
              error: null,
            });
          } catch (err: any) {
            clearTokens();
            set({
              user: null,
              accessToken: null,
              refreshToken: null,
              tokenExpiry: null,
              isAuthenticated: false,
              status: 'ERROR',
              isLoading: false,
              error: 'Cannot connect to Cauveris API. Please verify the backend is running.',
            });
          } finally {
            initAuthPromise = null;
          }
        })();

        return initAuthPromise;
      },

      // Login
      login: async (credentials: LoginRequest) => {
        set({ isLoading: true, error: null, status: 'CHECKING' });
        try {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000/api/v1';
          const response = await fetch(`${apiBase}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(credentials),
            credentials: 'include',
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const message = parseApiErrorMessage(errorData, `Login failed: ${response.status}`);
            throw new Error(message);
          }

          const data: TokenResponse = await response.json();

          // Store tokens
          storeTokens(data.access_token, data.refresh_token, data.expires_in);
          storeUser(data.user);

          // Update state
          set({
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            tokenExpiry: Date.now() + data.expires_in * 1000,
            user: data.user,
            isAuthenticated: true,
            status: 'AUTHENTICATED',
            isLoading: false,
            error: null,
          });
        } catch (err: any) {
          let errorMsg = err.message || 'Login failed';
          if (errorMsg === '[object Object]') {
            errorMsg = 'An unexpected error occurred during login.';
          } else if (errorMsg.includes('Failed to fetch') || errorMsg.includes('NetworkError')) {
            errorMsg = 'Cannot connect to Cauveris API. Please verify the backend is running.';
          }
          set({
            isLoading: false,
            error: errorMsg,
            isAuthenticated: false,
            status: errorMsg.includes('Cannot connect') ? 'ERROR' : 'UNAUTHENTICATED',
          });
          throw err;
        }
      },

      // Register / Signup
      register: async (data: RegisterRequest) => {
        set({ isLoading: true, error: null, status: 'CHECKING' });
        try {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000/api/v1';
          const response = await fetch(`${apiBase}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            credentials: 'include',
          });

          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const message = parseApiErrorMessage(errorData, `Registration failed: ${response.status}`);
            throw new Error(message);
          }

          const responseData: TokenResponse = await response.json();

          // Store tokens
          storeTokens(responseData.access_token, responseData.refresh_token, responseData.expires_in);
          storeUser(responseData.user);

          // Update state
          set({
            accessToken: responseData.access_token,
            refreshToken: responseData.refresh_token,
            tokenExpiry: Date.now() + responseData.expires_in * 1000,
            user: responseData.user,
            isAuthenticated: true,
            status: 'AUTHENTICATED',
            isLoading: false,
            error: null,
          });
        } catch (err: any) {
          let errorMsg = err.message || 'Registration failed';
          if (errorMsg === '[object Object]') {
            errorMsg = 'An unexpected error occurred during registration.';
          } else if (errorMsg.includes('Failed to fetch') || errorMsg.includes('NetworkError')) {
            errorMsg = 'Cannot connect to Cauveris API. Please verify the backend is running.';
          }
          set({
            isLoading: false,
            error: errorMsg,
            isAuthenticated: false,
            status: errorMsg.includes('Cannot connect') ? 'ERROR' : 'UNAUTHENTICATED',
          });
          throw err;
        }
      },

      // Logout
      logout: async () => {
        const { refreshToken, accessToken } = get();
        if (refreshToken || accessToken) {
          try {
            const apiBase = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000/api/v1';
            await fetch(`${apiBase}/auth/logout`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                ...(accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {}),
              },
              body: JSON.stringify({ refresh_token: refreshToken }),
              credentials: 'include',
            });
          } catch {
            // Ignore network errors during logout
          }
        }
        clearTokens();
        set({
          accessToken: null,
          refreshToken: null,
          tokenExpiry: null,
          user: null,
          isAuthenticated: false,
          status: 'UNAUTHENTICATED',
          isLoading: false,
          error: null,
        });
      },

      // Refresh access token
      refreshAccessToken: async () => {
        const { refreshToken } = get();
        if (!refreshToken) return false;

        // Single-flight guard: if a refresh is already in flight, wait for it
        if (refreshPromise) {
          return refreshPromise;
        }

        refreshPromise = (async () => {
          try {
            const apiBase = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000/api/v1';
            const response = await fetch(`${apiBase}/auth/refresh`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ refresh_token: refreshToken }),
              credentials: 'include',
            });

            if (!response.ok) {
              await get().logout();
              return false;
            }

            const data = await response.json();

            // Update tokens
            storeTokens(data.access_token, data.refresh_token, data.expires_in);
            set({
              accessToken: data.access_token,
              refreshToken: data.refresh_token,
              tokenExpiry: Date.now() + data.expires_in * 1000,
            });
            return true;
          } catch {
            await get().logout();
            return false;
          } finally {
            refreshPromise = null;
          }
        })();

        return refreshPromise;
      },
    }),
    {
      name: 'cauveris-auth-state',
      storage: createJSONStorage(() => localStorage),
      partialize: (state) => ({
        // Only persist user info, not tokens (tokens in separate localStorage)
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);

// Helper to get Authorization header
export function getAuthHeader(): string | null {
  const { accessToken } = useAuthStore.getState();
  if (!accessToken) return null;
  return `Bearer ${accessToken}`;
}

// Type for RequestInit without Node.js dependency
export interface FetchRequestInit extends Omit<RequestInit, 'headers'> {
  headers?: Record<string, string>;
}

// API client wrapper that automatically adds auth headers
export async function authenticatedFetch<T>(
  endpoint: string,
  options: FetchRequestInit = {}
): Promise<T> {
  const state = useAuthStore.getState();
  let accessToken = state.accessToken;
  const refreshToken = state.refreshToken;

  // Check if token is expired and try to refresh
  if (state.tokenExpiry && isTokenExpired(state.tokenExpiry)) {
    const refreshed = await state.refreshAccessToken();
    if (refreshed) {
      accessToken = useAuthStore.getState().accessToken;
    } else {
      // Refresh failed, user needs to login again
      await state.logout();
      throw new Error('Authentication expired. Please log in again.');
    }
  }

  const callerHeaders: Record<string, string> = options.headers || {};
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...callerHeaders,
  };

  if (accessToken) {
    // Auth header wins over any caller-supplied Authorization header
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  const url = `${process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000/api/v1'}${endpoint}`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15000);

  // Combine caller's signal with timeout signal so timeout still fires even if caller provides signal
  let effectiveSignal: AbortSignal;
  if (options.signal) {
    // Use AbortSignal.any if available, otherwise manually wire caller's signal to abort our controller
    if (typeof AbortSignal.any === 'function') {
      effectiveSignal = AbortSignal.any([options.signal, controller.signal]);
    } else {
      // Fallback: manually abort our controller when caller's signal aborts
      const abortHandler = () => controller.abort(options.signal?.reason);
      options.signal.addEventListener('abort', abortHandler, { once: true });
      // We'll need to remove this listener on cleanup
      effectiveSignal = controller.signal;
      // Store the handler for cleanup
      (effectiveSignal as any)._callerAbortHandler = abortHandler;
    }
  } else {
    effectiveSignal = controller.signal;
  }

  try {
    const response = await fetch(url, {
      ...options,
      signal: effectiveSignal,
      headers,
    });

    if (!response.ok) {
      // Handle 401 - try to refresh token once
      if (response.status === 401 && refreshToken) {
        const refreshed = await state.refreshAccessToken();
        if (refreshed) {
          // Retry with new token
          headers['Authorization'] = `Bearer ${useAuthStore.getState().accessToken}`;
          const retryResponse = await fetch(url, {
            ...options,
            signal: effectiveSignal,
            headers,
          });

          if (!retryResponse.ok) {
            const error = await handleApiError(retryResponse, endpoint);
            throw error;
          }
          return retryResponse.json();
        }
      }

      const error = await handleApiError(response, endpoint);
      throw error;
    }

    return response.json();
  } catch (err: any) {
    if (err instanceof CauverisError) throw err;
    if (err.name === 'AbortError') throw new Error(`Request timeout: ${endpoint}`);
    if (err.message?.includes('Failed to fetch')) {
      throw new Error(`Cannot connect to Cauveris API. Please verify the backend is running.`);
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
    // Clean up the signal listener if we added one
    if (options.signal && typeof AbortSignal.any !== 'function' && (effectiveSignal as any)._callerAbortHandler) {
      options.signal.removeEventListener('abort', (effectiveSignal as any)._callerAbortHandler);
    }
  }
}

export default useAuthStore;