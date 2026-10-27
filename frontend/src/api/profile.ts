import { apiFetch } from './client';
import type { components } from './schema';

// Types come from the generated OpenAPI schema (`make types`); never hand-write API shapes here.
export type UserProfile = components['schemas']['UserProfile'];
export type Diet = UserProfile['diets'][number];
export type Equipment = UserProfile['equipment'][number];

export const profileKeys = {
  profile: ['me', 'profile'] as const,
};

export const getProfile = (signal?: AbortSignal) =>
  apiFetch<UserProfile>('/api/v1/me/profile', { signal });

export const updateProfile = (body: UserProfile) =>
  apiFetch<UserProfile>('/api/v1/me/profile', { method: 'PUT', body: JSON.stringify(body) });
