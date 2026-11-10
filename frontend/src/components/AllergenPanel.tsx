import { useState } from 'react';
import type { AllergenAlert, IngredientAllergens } from '../api/recipes';
import { useRecipeAllergens } from '../hooks/useRecipes';

const LEVEL_LABEL: Record<AllergenAlert['level'], string> = {
  contains: 'є в складі',
  traces: 'можливі сліди',
  likely: 'імовірно є',
};

const list = (items: string[]) => items.join(', ');

function IngredientNote({ row }: { row: IngredientAllergens }) {
  const declared = row.source === 'declared';
  return (
    <span className="text-olive-800">
      {declared ? (
        <>
          <strong>
            Попередження: {row.contains.length === 1 ? 'алерген' : 'алергени'}{' '}
            {list(row.contains.length > 0 ? row.contains : row.traces)}
          </strong>
          {row.contains.length > 0 && row.traces.length > 0
            ? `. Можливі сліди: ${list(row.traces)}`
            : null}
          .
        </>
      ) : (
        <strong>Попередження: можливі алергени.</strong>
      )}{' '}
      Перевірте склад самі
      {row.product_url ? (
        <>
          {' '}
          на упаковці або на{' '}
          <a
            href={row.product_url}
            target="_blank"
            rel="noreferrer"
            className="underline hover:text-olive-600"
          >
            сторінці товару
          </a>
        </>
      ) : (
        ' на упаковці'
      )}
      .
    </span>
  );
}

export function AllergenPanel({ recipeId }: { recipeId: number }) {
  const [requested, setRequested] = useState(false);
  const check = useRecipeAllergens(recipeId, requested);
  const data = check.data;

  if (!requested) {
    return (
      <section className="border-cream-200 border-t px-6 py-6 sm:px-8">
        <h3 className="font-display text-xl font-bold">Алергени в продуктах</h3>
        <p className="mt-2 text-sm text-olive-800">
          Дивимось, що Сільпо вказує про алергени в продуктах рецепта. Це лише попередження, а не
          гарантія: дані є не для всіх товарів, тож завжди перевіряйте склад самі.
        </p>
        <button
          type="button"
          onClick={() => setRequested(true)}
          className="text-cream-50 focus:ring-accent-500 mt-3 min-h-10 rounded-xl bg-olive-800 px-4 font-semibold transition hover:bg-olive-900 focus:ring-2 focus:outline-none"
        >
          Перевірити алергени
        </button>
      </section>
    );
  }

  return (
    <section className="border-cream-200 border-t px-6 py-6 sm:px-8" aria-busy={check.isFetching}>
      <h3 className="font-display text-xl font-bold">Алергени в продуктах</h3>

      {check.isPending ? (
        <p role="status" className="mt-4 animate-pulse text-sm text-olive-800">
          Перевіряємо продукти в Сільпо…
        </p>
      ) : null}
      {check.isError ? (
        <p role="alert" className="text-accent-600 mt-4 text-sm font-medium">
          {check.error.message}
        </p>
      ) : null}

      {data ? (
        <div className="mt-4 space-y-3">
          {!data.silpo_checked ? (
            <p role="status" className="bg-cream-100 rounded-xl px-4 py-3 text-sm text-olive-900">
              Сільпо зараз не відповіло, тож даних із нього немає. Перевірте склад на упаковці.
            </p>
          ) : null}
          {!data.profile_applied ? (
            <p className="bg-cream-100 rounded-xl px-4 py-3 text-sm text-olive-900">
              Увійдіть і вкажіть свої алергени в профілі, щоб побачити, що з цього вас стосується.
            </p>
          ) : null}
          {data.has_alerts ? (
            <p
              role="alert"
              className="text-accent-600 rounded-xl bg-olive-100 px-4 py-3 text-sm font-semibold"
            >
              Увага: у продуктах цього рецепта можуть бути ваші алергени. Перегляньте список нижче.
            </p>
          ) : null}

          <ul className="divide-cream-200 divide-y text-sm">
            {data.ingredients.map((row, idx) => (
              <li key={`${row.name}-${idx}`} className="py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <span className="font-medium text-olive-900">
                    {row.name}
                    {row.product_name ? (
                      <span className="font-normal text-olive-600"> · {row.product_name}</span>
                    ) : null}
                  </span>
                  {row.alerts.map((a) => (
                    <span key={a.allergy} className="text-accent-600 font-semibold">
                      Ваш алерген: {a.allergy} ({LEVEL_LABEL[a.level]})
                    </span>
                  ))}
                </div>
                <p className="mt-0.5">
                  <IngredientNote row={row} />
                </p>
              </li>
            ))}
          </ul>
          <p className="text-sm text-olive-600">
            Дані Сільпо неповні, а склад може змінюватись. Відсутність попередження не означає, що
            алергенів немає.
          </p>
        </div>
      ) : null}
    </section>
  );
}
