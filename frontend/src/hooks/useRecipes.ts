import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createRecipe, getRecipe, recipeKeys } from '../api/recipes';

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
