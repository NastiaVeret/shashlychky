import { useState } from 'react';
import type { Alternative, Purchase, ShoppingLine } from '../api/recipes';
import { useRecipeShoppingList } from '../hooks/useRecipes';

const STATUS_NOTE: Record<ShoppingLine['status'], string> = {
  at_home: 'вже є вдома',
  to_taste: 'за смаком',
  no_product: 'не знайдено в Сільпо',
  out_of_stock: 'немає в наявності',
  partial_stock: 'на складі менше, ніж потрібно',
  unknown_package: 'фасування не вдалося перерахувати',
  ok: '',
};

const money = (n: number) => `${n.toFixed(2).replace('.', ',')} ₴`;
const amount = (n: number) => String(Number(n.toFixed(3))).replace('.', ',');

function purchaseText(p: Purchase): string {
  const what = p.quantity_unit === 'kg' ? `${amount(p.quantity)} кг` : `${amount(p.quantity)} уп.`;
  const approx = p.estimated ? '≈ ' : '';
  return p.total_price !== null ? `${approx}${what} · ${money(p.total_price)}` : `${approx}${what}`;
}

/** How the recipe amount became grams, when it is an estimate (a mass is exact and needs no note). */
function gramsNote(line: ShoppingLine): string | null {
  if (line.needed_g === null || line.grams_basis === null || line.grams_basis === 'exact') {
    return null;
  }
  const grams = `≈ ${amount(line.needed_g)} г`;
  switch (line.grams_basis) {
    case 'density':
      return `${grams} (за густиною: 1 мл ≈ ${amount(line.grams_per_unit ?? 1)} г)`;
    case 'density_assumed':
      return `${grams} (густину продукту не знайдено, рахуємо як воду)`;
    case 'piece_weight':
      return `${grams} (середня вага штуки ≈ ${amount(line.grams_per_unit ?? 0)} г)`;
  }
}

function AlternativeRow({ alt }: { alt: Alternative }) {
  return (
    <li className="py-1.5 text-sm">
      {alt.url ? (
        <a
          href={alt.url}
          target="_blank"
          rel="noreferrer"
          className="font-medium underline hover:text-olive-800"
        >
          {alt.name}
        </a>
      ) : (
        <span className="font-medium">{alt.name}</span>
      )}
      {alt.package ? <span className="text-olive-600"> · {alt.package}</span> : null}
      {alt.price !== null ? <span className="text-olive-600"> · {money(alt.price)}</span> : null}
      <span className="text-olive-600">
        {' · '}
        {alt.enough_stock ? 'вистачає' : 'вистачає не повністю'}
      </span>
      {alt.alerts.map((a) => (
        <span key={a.allergy} className="text-accent-600 font-semibold">
          {' · '}
          ваш алерген: {a.allergy}
        </span>
      ))}
      {alt.allergen_source === 'unknown' ? (
        <span className="text-olive-600"> · алергени не вказані, перевірте склад</span>
      ) : null}
    </li>
  );
}

function Line({ line }: { line: ShoppingLine }) {
  const note = STATUS_NOTE[line.status];
  const quiet = line.status === 'at_home' || line.status === 'to_taste';
  return (
    <li className="py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className={quiet ? 'text-olive-600' : 'font-medium text-olive-900'}>
          {line.name}
          {line.quantity !== null ? (
            <span className="font-normal text-olive-600">
              {' '}
              · {amount(line.quantity)} {line.unit}
            </span>
          ) : null}
        </span>
        {line.purchase ? (
          <span
            className={line.status === 'ok' ? 'font-semibold text-olive-800' : 'text-olive-600'}
          >
            {purchaseText(line.purchase)}
          </span>
        ) : null}
      </div>
      {gramsNote(line) ? <p className="mt-0.5 text-sm text-olive-600">{gramsNote(line)}</p> : null}
      {line.product ? (
        <p className="mt-0.5 text-sm text-olive-600">
          {line.product.url ? (
            <a
              href={line.product.url}
              target="_blank"
              rel="noreferrer"
              className="underline hover:text-olive-800"
            >
              {line.product.name}
            </a>
          ) : (
            line.product.name
          )}
          {line.product.package ? ` · в упаковці ${line.product.package}` : null}
          {line.product.stock !== null ? ` · залишок ${amount(line.product.stock)}` : null}
        </p>
      ) : null}
      {note ? (
        <p className={`mt-0.5 text-sm ${quiet ? 'text-olive-600' : 'text-accent-600 font-medium'}`}>
          {note}
        </p>
      ) : null}
      {line.alternatives.length > 0 ? (
        <div className="mt-1">
          <p className="text-sm font-medium text-olive-800">Можна замінити на:</p>
          <ul className="divide-cream-200 divide-y">
            {line.alternatives.map((alt, idx) => (
              <AlternativeRow key={`${alt.name}-${idx}`} alt={alt} />
            ))}
          </ul>
        </div>
      ) : null}
    </li>
  );
}

export function ShoppingPanel({ recipeId }: { recipeId: number }) {
  const [requested, setRequested] = useState(false);
  const list = useRecipeShoppingList(recipeId, requested);
  const data = list.data;

  if (!requested) {
    return (
      <section className="border-cream-200 border-t px-6 py-6 sm:px-8">
        <h3 className="font-display text-xl font-bold">Що купити в Сільпо</h3>
        <p className="mt-2 text-sm text-olive-800">
          Підбираємо товари для інгредієнтів, яких у вас немає, рахуємо упаковки й дивимось залишки.
        </p>
        <button
          type="button"
          onClick={() => setRequested(true)}
          className="text-cream-50 focus:ring-accent-500 mt-3 min-h-10 rounded-xl bg-olive-800 px-4 font-semibold transition hover:bg-olive-900 focus:ring-2 focus:outline-none"
        >
          Скласти список покупок
        </button>
      </section>
    );
  }

  return (
    <section className="border-cream-200 border-t px-6 py-6 sm:px-8" aria-busy={list.isFetching}>
      <h3 className="font-display text-xl font-bold">Що купити в Сільпо</h3>

      {list.isPending ? (
        <p role="status" className="mt-4 animate-pulse text-sm text-olive-800">
          Шукаємо товари в Сільпо…
        </p>
      ) : null}
      {list.isError ? (
        <p role="alert" className="text-accent-600 mt-4 text-sm font-medium">
          {list.error.message}
        </p>
      ) : null}

      {data ? (
        <div className="mt-4 space-y-3">
          {data.needs_attention > 0 ? (
            <p className="bg-cream-100 rounded-xl px-4 py-3 text-sm text-olive-900">
              Потребують уваги: {data.needs_attention}. Для них нижче показано, що відомо від
              Сільпо.
            </p>
          ) : null}
          <ul className="divide-cream-200 divide-y">
            {data.lines.map((line, idx) => (
              <Line key={`${line.name}-${idx}`} line={line} />
            ))}
          </ul>
          {data.total_price !== null ? (
            <p className="text-right font-semibold text-olive-900">
              Разом за готовими до покупки позиціями: {money(data.total_price)}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
