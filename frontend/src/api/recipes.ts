import { apiFetch } from './client';
import type { components } from './schema';

// Types come from the generated OpenAPI schema (`make types`); never hand-write API shapes here.
export type RecipeRequest = components['schemas']['RecipeRequest'];
export type Ingredient = components['schemas']['Ingredient'];
export type RecipeRead = components['schemas']['RecipeRead'];

export const recipeKeys = {
  all: ['recipes'] as const,
  detail: (id: number) => ['recipes', id] as const,
};

export const createRecipe = (body: RecipeRequest) =>
  apiFetch<RecipeRead>('/api/v1/recipes', { method: 'POST', body: JSON.stringify(body) });

export const getRecipe = (id: number, signal?: AbortSignal) =>
  apiFetch<RecipeRead>(`/api/v1/recipes/${id}`, { signal });
