import { apiFetch } from './client';

// Mirrors backend/app/schemas/recipes.py

export interface RecipeRequest {
  products: string[];
  preferences?: string | null;
  servings?: number;
}

export interface Ingredient {
  name: string;
  quantity: number | null;
  unit: string;
  have_at_home: boolean;
}

export interface RecipeContent {
  title: string;
  description: string;
  cooking_time_minutes: number;
  servings: number;
  ingredients: Ingredient[];
  steps: string[];
  tips: string | null;
  clarifying_question: string | null;
}

export interface RecipeRead extends RecipeContent {
  id: number;
  products: string[];
  created_at: string;
}

export const recipeKeys = {
  all: ['recipes'] as const,
  detail: (id: number) => ['recipes', id] as const,
};

export const createRecipe = (body: RecipeRequest) =>
  apiFetch<RecipeRead>('/api/v1/recipes', { method: 'POST', body: JSON.stringify(body) });

export const getRecipe = (id: number, signal?: AbortSignal) =>
  apiFetch<RecipeRead>(`/api/v1/recipes/${id}`, { signal });
