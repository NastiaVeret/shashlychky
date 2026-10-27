import { Link, useParams } from 'react-router-dom';
import { RecipeCard } from '../components/RecipeCard';
import { useRecipe } from '../hooks/useRecipes';

export function RecipePage() {
  const { id } = useParams();
  const recipe = useRecipe(Number(id));

  return (
    <div className="space-y-6 pt-8">
      <Link to="/" className="text-sm font-medium text-olive-900 underline hover:text-olive-800">
        ← Новий рецепт
      </Link>
      {recipe.isPending ? (
        <div role="status" className="rounded-card bg-cream-50/70 animate-pulse p-8 text-center">
          Завантажуємо рецепт…
        </div>
      ) : null}
      {recipe.isError ? (
        <p role="alert" className="rounded-card bg-cream-50 text-accent-600 p-6 font-medium">
          {recipe.error.message}
        </p>
      ) : null}
      {recipe.data ? <RecipeCard recipe={recipe.data} /> : null}
    </div>
  );
}
