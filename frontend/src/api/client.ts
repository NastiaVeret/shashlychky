// Base HTTP client. BASE_URL is empty by default: in dev Vite proxies /api to the backend,
// in production Firebase Hosting rewrites /api/** to the Cloud Run service (same origin).
// VITE_API_URL exists only for pointing a local build at a remote backend.
const BASE_URL = import.meta.env.VITE_API_URL ?? '';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    throw new ApiError(res.status, await res.text());
  }
  return res.json() as Promise<T>;
}

export interface HealthResponse {
  status: string;
  version: string;
}

export const getHealth = () => apiFetch<HealthResponse>('/api/v1/health');
