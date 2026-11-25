import { apiFetch } from './client';
import type { components } from './schema';

// Types come from the generated OpenAPI schema (`make types`); never hand-write API shapes here.
// Silpo tokens never leave the server; the frontend only sees whether an account is connected.
export type SilpoConnection = components['schemas']['SilpoConnectionRead'];
export type SilpoAuthorize = components['schemas']['SilpoAuthorizeRead'];

export const silpoKeys = {
  connection: ['me', 'silpo'] as const,
};

export const getSilpoConnection = (signal?: AbortSignal) =>
  apiFetch<SilpoConnection>('/api/v1/silpo/connection', { signal });

/** Starts the Silpo login; the browser must then navigate to `authorize_url`. 503 if Silpo fails. */
export const startSilpoConnection = () =>
  apiFetch<SilpoAuthorize>('/api/v1/silpo/connection', { method: 'POST' });

/** Idempotent: disconnecting an account that is not connected is still 204. */
export const deleteSilpoConnection = () =>
  apiFetch<void>('/api/v1/silpo/connection', { method: 'DELETE' });

export type CartAddRequest = components['schemas']['CartAddRequest'];
export type CartItem = components['schemas']['CartItem'];
export type CartAddResult = components['schemas']['CartAddResult'];

/** Puts products into the user's own Silpo cart. The answer is what the cart holds afterwards.
 * 409 when Silpo is not connected or the cart cannot take products now (no address, no slots). */
export const addToSilpoCart = (body: CartAddRequest) =>
  apiFetch<CartAddResult>('/api/v1/silpo/cart', { method: 'POST', body: JSON.stringify(body) });
