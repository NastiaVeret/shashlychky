import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createRecipe, getMyRecipes, getRecipe, recipeKeys } from '../api/recipes';

export function useCreateRecipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: createRecipe,
    onSuccess: (recipe) => {
      qc.setQueryData(recipeKeys.detail(recipe.id), recipe);
      void qc.invalidateQueries({ queryKey: recipeKeys.mine });
    },
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

/** Pass `enabled = !!user`: the endpoint requires a session. */
export function useMyRecipes(enabled: boolean) {
  return useQuery({
    queryKey: recipeKeys.mine,
    queryFn: ({ signal }) => getMyRecipes({ limit: 50, offset: 0 }, signal),
    enabled,
  });
}
