import { Link, Navigate } from 'react-router-dom';
import { useMe } from '../hooks/useAuth';
import { useMyRecipes } from '../hooks/useRecipes';

const DATE = new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', year: 'numeric' });

export function MyRecipesPage() {
  const me = useMe();
  const recipes = useMyRecipes(!!me.data);

  if (me.isPending) return null;
  // A failed /me is not "logged out": do not bounce a user with a valid cookie to /login.
  if (me.isError) {
    return (
      <p role="alert" className="rounded-card bg-cream-50 text-accent-600 mt-8 p-6 font-medium">
        {me.error.message}
      </p>
    );
  }
  if (!me.data) return <Navigate to="/login" replace />;

  return (
    <div className="space-y-6 pt-8">
      <h1 className="font-display text-4xl font-black text-olive-900">Мої рецепти</h1>

      {recipes.isPending ? (
        <div role="status" className="rounded-card bg-cream-50/70 animate-pulse p-8 text-center">
          Завантажуємо рецепти…
        </div>
      ) : null}
      {recipes.isError ? (
        <p role="alert" className="rounded-card bg-cream-50 text-accent-600 p-6 font-medium">
          {recipes.error.message}
        </p>
      ) : null}

      {recipes.data?.length === 0 ? (
        <div className="rounded-card bg-cream-100 shadow-card space-y-3 p-8 text-center">
          <p className="text-olive-800">Тут з'являться рецепти, які ви придумаєте.</p>
          <Link
            to="/"
            className="focus:ring-accent-500 inline-block font-semibold text-olive-900 underline hover:text-olive-800 focus:rounded focus:ring-2 focus:outline-none"
          >
            Придумати перший рецепт
          </Link>
        </div>
      ) : null}

      {recipes.data && recipes.data.length > 0 ? (
        <ul className="grid gap-4 sm:grid-cols-2">
          {recipes.data.map((r) => (
            <li key={r.id}>
              <Link
                to={`/recipes/${r.id}`}
                className="rounded-card bg-cream-50 shadow-card focus:ring-accent-500 block h-full p-5 transition hover:-translate-y-0.5 focus:ring-2 focus:outline-none"
              >
                <h2 className="font-display text-xl font-bold text-olive-900">{r.title}</h2>
                <p className="mt-1 line-clamp-2 text-sm text-olive-800">{r.description}</p>
                <p className="mt-3 text-xs text-olive-800/70">
                  {DATE.format(new Date(r.created_at))} · {r.cooking_time_minutes} хв ·{' '}
                  {r.products.join(', ')}
                </p>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
