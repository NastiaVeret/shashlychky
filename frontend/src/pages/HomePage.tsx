import { useState, type FormEvent } from 'react';
import { ProductInput } from '../components/ProductInput';
import { RecipeCard } from '../components/RecipeCard';
import { useCreateRecipe } from '../hooks/useRecipes';

const SERVINGS = [1, 2, 4, 6] as const;

export function HomePage() {
  const [products, setProducts] = useState<string[]>([]);
  const [servings, setServings] = useState<number>(2);
  const [preferences, setPreferences] = useState('');
  const create = useCreateRecipe();

  const canSubmit = products.length > 0 && !create.isPending;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    create.mutate({ products, servings, preferences: preferences.trim() || null });
  };

  return (
    <div className="space-y-10">
      <section className="pt-8 sm:pt-14">
        <h1 className="font-display text-4xl leading-tight font-black text-olive-900 sm:text-6xl">
          Що приготувати
          <br />
          <span className="text-cream-50">з того, що є?</span>
        </h1>
        <p className="mt-4 max-w-xl text-lg text-olive-900/85">
          Перелічіть продукти з холодильника, і ми запропонуємо страву, яку можна зробити саме з
          них.
        </p>
      </section>

      <form
        onSubmit={onSubmit}
        className="rounded-card bg-cream-100 shadow-card space-y-6 p-5 sm:p-8"
        aria-busy={create.isPending}
      >
        <ProductInput products={products} onChange={setProducts} disabled={create.isPending} />

        <div className="grid gap-6 sm:grid-cols-2">
          <fieldset>
            <legend className="mb-2 text-sm font-semibold text-olive-800">Порцій</legend>
            <div className="flex gap-2">
              {SERVINGS.map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setServings(n)}
                  aria-pressed={servings === n}
                  className="bg-cream-50 focus:ring-accent-500 aria-pressed:text-cream-50 flex-1 rounded-xl border-2 border-olive-200 py-2 font-semibold transition hover:border-olive-400 focus:ring-2 focus:outline-none aria-pressed:border-olive-800 aria-pressed:bg-olive-800"
                >
                  {n}
                </button>
              ))}
            </div>
          </fieldset>
          <div>
            <label
              htmlFor="preferences"
              className="mb-2 block text-sm font-semibold text-olive-800"
            >
              Побажання <span className="font-normal text-olive-600">(необов'язково)</span>
            </label>
            <input
              id="preferences"
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              maxLength={200}
              placeholder="швидко, без м'яса, на сніданок…"
              className="bg-cream-50 focus:border-accent-500 focus:ring-accent-500/20 w-full rounded-xl border-2 border-olive-200 px-3 py-2 transition outline-none placeholder:text-olive-600/60 focus:ring-4"
            />
          </div>
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="submit"
            disabled={!canSubmit}
            className="bg-accent-500 text-cream-50 hover:bg-accent-600 focus:ring-accent-500/40 rounded-xl px-6 py-3 text-base font-bold shadow-sm transition focus:ring-4 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {create.isPending ? 'Думаємо над рецептом…' : 'Придумати рецепт'}
          </button>
          {create.isError ? (
            <p role="alert" className="text-accent-600 text-sm font-medium">
              {create.error.message}
            </p>
          ) : null}
        </div>
      </form>

      {create.isPending ? (
        <div
          role="status"
          className="rounded-card bg-cream-50/70 animate-pulse p-8 text-center text-olive-800"
        >
          Підбираємо страву з ваших продуктів, це займе кілька секунд…
        </div>
      ) : null}

      {create.data ? (
        <section className="space-y-3">
          <RecipeCard recipe={create.data} />
          <p className="text-right text-xs text-olive-800/70">
            Посилання на рецепт:{' '}
            <a href={`/recipes/${create.data.id}`} className="underline hover:text-olive-900">
              /recipes/{create.data.id}
            </a>
          </p>
        </section>
      ) : null}
    </div>
  );
}
