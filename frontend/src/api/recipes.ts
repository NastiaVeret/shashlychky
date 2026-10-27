import { apiFetch } from './client';
import type { components } from './schema';

// Types come from the generated OpenAPI schema (`make types`); never hand-write API shapes here.
export type RecipeRequest = components['schemas']['RecipeRequest'];
export type Ingredient = components['schemas']['IngredientRead'];
export type RecipeRead = components['schemas']['RecipeRead'];

export const recipeKeys = {
  all: ['recipes'] as const,
  mine: ['recipes', 'mine'] as const,
  detail: (id: number) => ['recipes', id] as const,
};

export const createRecipe = (body: RecipeRequest) =>
  apiFetch<RecipeRead>('/api/v1/recipes', { method: 'POST', body: JSON.stringify(body) });

export const getRecipe = (id: number, signal?: AbortSignal) =>
  apiFetch<RecipeRead>(`/api/v1/recipes/${id}`, { signal });

/** The logged-in user's recipes, newest first. `limit` is 1..50 on the backend. */
export const getMyRecipes = (
  { limit, offset }: { limit: number; offset: number },
  signal?: AbortSignal,
) => {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiFetch<RecipeRead[]>(`/api/v1/me/recipes?${params}`, { signal });
};

export type RecipeNutrition = components['schemas']['RecipeNutrition'];
export type NutritionFacts = components['schemas']['NutritionFacts'];

export const nutritionKeys = {
  detail: (id: number) => ['recipes', id, 'nutrition'] as const,
};

// The goal comparison is pure arithmetic on the client; the server is asked once per recipe.
export const getRecipeNutrition = (id: number, signal?: AbortSignal) =>
  apiFetch<RecipeNutrition>(`/api/v1/recipes/${id}/nutrition`, { signal });
