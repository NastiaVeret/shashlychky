import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createRecipe,
  getRecipe,
  getRecipeNutrition,
  nutritionKeys,
  recipeKeys,
} from '../api/recipes';

export function useCreateRecipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRecipe,
    onSuccess: (recipe) => qc.setQueryData(recipeKeys.detail(recipe.id), recipe),
  });
}

export function useRecipe(id: number) {
  return useQuery({
    queryKey: recipeKeys.detail(id),
    queryFn: ({ signal }) => getRecipe(id, signal),
    staleTime: Infinity, // a stored recipe never changes
    enabled: Number.isFinite(id) && id > 0,
  });
}

export function useRecipeNutrition(id: number, dailyKcalGoal: number | null) {
  return useQuery({
    queryKey: nutritionKeys.detail(id, dailyKcalGoal),
    queryFn: ({ signal }) => getRecipeNutrition(id, dailyKcalGoal, signal),
    staleTime: 5 * 60 * 1000, // Silpo product data changes rarely
    retry: 1, // 503 when Silpo is unavailable: show it quickly instead of retrying 3 times
    enabled: Number.isFinite(id) && id > 0,
  });
}
