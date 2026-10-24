import type { Ingredient, RecipeRead } from '../api/recipes';

function formatQuantity(i: Ingredient): string {
  if (i.quantity === null) return i.unit;
  const q = Number.isInteger(i.quantity) ? i.quantity : i.quantity.toFixed(1).replace(/\.0$/, '');
  return `${q} ${i.unit}`;
}

export function RecipeCard({ recipe }: { recipe: RecipeRead }) {
  const toBuy = recipe.ingredients.filter((i) => !i.have_at_home);

  return (
    <article className="rounded-card bg-cream-50 shadow-card overflow-hidden">
      <header className="border-cream-200 bg-cream-100 border-b px-6 py-5 sm:px-8">
        <h2 className="font-display text-3xl font-bold text-olive-900 sm:text-4xl">
          {recipe.title}
        </h2>
        <p className="mt-2 text-olive-800">{recipe.description}</p>
        <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <div className="flex items-center gap-2">
            <dt className="text-olive-600">Час</dt>
            <dd className="font-semibold">{recipe.cooking_time_minutes} хв</dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-olive-600">Порцій</dt>
            <dd className="font-semibold">{recipe.servings}</dd>
          </div>
          {toBuy.length > 0 ? (
            <div className="flex items-center gap-2">
              <dt className="text-olive-600">Докупити</dt>
              <dd className="text-accent-600 font-semibold">{toBuy.length}</dd>
            </div>
          ) : (
            <div className="rounded-full bg-olive-100 px-3 py-0.5 font-semibold text-olive-800">
              Усе є вдома
            </div>
          )}
        </dl>
      </header>

      {recipe.clarifying_question ? (
        <div className="border-accent-400/60 bg-accent-400/10 mx-6 mt-5 rounded-xl border px-4 py-3 text-sm text-olive-900 sm:mx-8">
          <span className="font-semibold">Уточнення: </span>
          {recipe.clarifying_question}
        </div>
      ) : null}

      <div className="grid gap-8 px-6 py-6 sm:px-8 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section>
          <h3 className="font-display text-xl font-bold">Інгредієнти</h3>
          <ul className="divide-cream-200 mt-3 divide-y">
            {recipe.ingredients.map((i) => (
              <li key={i.name} className="flex items-start justify-between gap-3 py-2 text-sm">
                <span className="flex items-center gap-2">
                  <span
                    aria-hidden
                    className={`size-2 shrink-0 rounded-full ${i.have_at_home ? 'bg-olive-600' : 'bg-accent-500'}`}
                  />
                  <span>{i.name}</span>
                  {!i.have_at_home && (
                    <span className="bg-accent-500/15 text-accent-600 rounded-full px-2 py-0.5 text-xs font-medium">
                      докупити
                    </span>
                  )}
                </span>
                <span className="shrink-0 font-medium text-olive-800">{formatQuantity(i)}</span>
              </li>
            ))}
          </ul>
        </section>

        <section>
          <h3 className="font-display text-xl font-bold">Приготування</h3>
          <ol className="mt-3 space-y-3">
            {recipe.steps.map((step, idx) => (
              <li key={idx} className="flex gap-3">
                <span className="text-cream-50 flex size-7 shrink-0 items-center justify-center rounded-full bg-olive-800 text-sm font-bold">
                  {idx + 1}
                </span>
                <p className="pt-0.5 text-olive-900">{step}</p>
              </li>
            ))}
          </ol>
          {recipe.tips ? (
            <p className="mt-5 rounded-xl bg-olive-100 px-4 py-3 text-sm text-olive-800">
              <span className="font-semibold">Порада: </span>
              {recipe.tips}
            </p>
          ) : null}
        </section>
      </div>
    </article>
  );
}
