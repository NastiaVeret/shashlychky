import { useState, type FormEvent } from 'react';
import type { NutritionFacts, RecipeNutrition } from '../api/recipes';
import { useRecipeNutrition } from '../hooks/useRecipes';

const MIN_GOAL = 800;
const MAX_GOAL = 6000;

const STATUS_LABEL: Record<RecipeNutrition['ingredients'][number]['status'], string> = {
  counted: 'враховано',
  to_taste: 'за смаком',
  no_product: 'немає в Сільпо',
  no_data: 'немає КБЖВ',
  unknown_unit: 'невідома вага',
};

const fmt = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1));

function FactsRow({ label, facts }: { label: string; facts: NutritionFacts }) {
  return (
    <tr className="border-cream-200 border-t">
      <th scope="row" className="py-2 pr-3 text-left font-medium text-olive-800">
        {label}
      </th>
      <td className="py-2 text-right font-semibold">{fmt(facts.kcal)}</td>
      <td className="py-2 text-right">{fmt(facts.protein_g)}</td>
      <td className="py-2 text-right">{fmt(facts.fat_g)}</td>
      <td className="py-2 text-right">{fmt(facts.carbs_g)}</td>
    </tr>
  );
}

export function NutritionPanel({ recipeId }: { recipeId: number }) {
  const [goalInput, setGoalInput] = useState('');
  const [goal, setGoal] = useState<number | null>(null);
  const nutrition = useRecipeNutrition(recipeId, goal);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const value = Number(goalInput);
    setGoal(goalInput && value >= MIN_GOAL && value <= MAX_GOAL ? Math.round(value) : null);
  };

  const data = nutrition.data;

  return (
    <section
      className="border-cream-200 border-t px-6 py-6 sm:px-8"
      aria-busy={nutrition.isFetching}
    >
      <h3 className="font-display text-xl font-bold">КБЖВ</h3>

      <form onSubmit={onSubmit} className="mt-3 flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor="kcal-goal" className="mb-1 block text-sm font-semibold text-olive-800">
            Денна норма, ккал <span className="font-normal text-olive-600">(необов'язково)</span>
          </label>
          <input
            id="kcal-goal"
            type="number"
            inputMode="numeric"
            min={MIN_GOAL}
            max={MAX_GOAL}
            step={50}
            value={goalInput}
            onChange={(e) => setGoalInput(e.target.value)}
            placeholder="2000"
            className="bg-cream-50 focus:border-accent-500 focus:ring-accent-500/20 w-36 rounded-xl border-2 border-olive-200 px-3 py-2 transition outline-none focus:ring-4"
          />
        </div>
        <button
          type="submit"
          className="text-cream-50 focus:ring-accent-500 rounded-xl bg-olive-800 px-4 py-2 font-semibold transition hover:bg-olive-900 focus:ring-2 focus:outline-none"
        >
          Порівняти
        </button>
      </form>

      {nutrition.isPending ? (
        <p role="status" className="mt-4 animate-pulse text-sm text-olive-800">
          Рахуємо КБЖВ за даними Сільпо…
        </p>
      ) : null}
      {nutrition.isError ? (
        <p role="alert" className="text-accent-600 mt-4 text-sm font-medium">
          {nutrition.error.message}
        </p>
      ) : null}

      {data ? (
        <div className="mt-4 space-y-3">
          {data.counted_ingredients === 0 ? (
            <p className="bg-cream-100 rounded-xl px-4 py-3 text-sm text-olive-900">
              У Сільпо не знайшлося даних КБЖВ для жодного інгредієнта, тож порахувати страву не
              вдалося.
            </p>
          ) : null}
          {data.counted_ingredients > 0 && data.goal ? (
            <p className="rounded-xl bg-olive-100 px-4 py-3 text-sm text-olive-900">
              Одна порція —{' '}
              <span className="font-semibold">{fmt(data.goal.per_serving_percent)}%</span> від
              денної норми {data.goal.daily_kcal} ккал
            </p>
          ) : null}

          {data.counted_ingredients > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-olive-600">
                  <th scope="col" className="sr-only">
                    Частина
                  </th>
                  <th scope="col" className="pb-1 text-right font-medium">
                    ккал
                  </th>
                  <th scope="col" className="pb-1 text-right font-medium">
                    Б, г
                  </th>
                  <th scope="col" className="pb-1 text-right font-medium">
                    Ж, г
                  </th>
                  <th scope="col" className="pb-1 text-right font-medium">
                    В, г
                  </th>
                </tr>
              </thead>
              <tbody>
                <FactsRow label="Порція" facts={data.per_serving} />
                <FactsRow label={`Уся страва (${data.servings} порц.)`} facts={data.total} />
              </tbody>
            </table>
          ) : null}

          <details className="text-sm">
            <summary className="cursor-pointer text-olive-800">
              Враховано {data.counted_ingredients} з {data.countable_ingredients} інгредієнтів (дані
              Сільпо)
            </summary>
            <ul className="divide-cream-200 mt-2 divide-y">
              {data.ingredients.map((i) => (
                <li key={i.name} className="flex justify-between gap-3 py-1.5">
                  <span>
                    {i.name}
                    {i.product_name ? (
                      <span className="text-olive-600"> · {i.product_name}</span>
                    ) : null}
                  </span>
                  <span
                    className={`shrink-0 ${i.status === 'counted' ? 'font-medium text-olive-800' : 'text-olive-600'}`}
                  >
                    {i.total ? `${fmt(i.total.kcal)} ккал` : STATUS_LABEL[i.status]}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </div>
      ) : null}
    </section>
  );
}
