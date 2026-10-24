// Base HTTP client. BASE_URL is empty by default: in dev Vite proxies /api to the backend,
// in production Firebase Hosting rewrites /api/** to the Cloud Run service (same origin).
// VITE_API_URL exists only for pointing a local build at a remote backend.
import type { components } from './schema';

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Pulls FastAPI's `{"detail": ...}` out of an error body, falling back to a generic message. */
async function errorMessage(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string') return detail;
    }
  } catch {
    // not JSON
  }
  return res.status >= 500 ? 'Сервер тимчасово недоступний' : 'Помилка запиту';
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    throw new ApiError(res.status, await errorMessage(res));
  }
  return res.json() as Promise<T>;
}

export type HealthResponse = components['schemas']['HealthResponse'];

export const getHealth = () => apiFetch<HealthResponse>('/api/v1/health');
