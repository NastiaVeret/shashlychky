import { ApiError, apiFetch } from './client';
import type { components } from './schema';

// Types come from the generated OpenAPI schema (`make types`); never hand-write API shapes here.
// The session lives in the httpOnly `__session` cookie; same-origin fetch sends it automatically.
export type UserRead = components['schemas']['UserRead'];
export type LoginRequest = components['schemas']['LoginRequest'];
export type RegisterRequest = components['schemas']['RegisterRequest'];

export const meKeys = {
  me: ['me'] as const,
};

export const register = (body: RegisterRequest) =>
  apiFetch<UserRead>('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(body) });

export const login = (body: LoginRequest) =>
  apiFetch<UserRead>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(body) });

export const logout = () => apiFetch<void>('/api/v1/auth/logout', { method: 'POST' });

/** The logged-in user, or `null` when there is no valid session (401 is a normal state here). */
export const getMe = async (signal?: AbortSignal): Promise<UserRead | null> => {
  try {
    return await apiFetch<UserRead>('/api/v1/me', { signal });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
};

export const deleteMe = () => apiFetch<void>('/api/v1/me', { method: 'DELETE' });
