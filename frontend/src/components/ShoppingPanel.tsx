import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Alternative, Purchase, ShoppingLine } from '../api/recipes';
import type { CartAddResult, CartItem } from '../api/silpo';
import { useMe } from '../hooks/useAuth';
import { useRecipeShoppingList } from '../hooks/useRecipes';
import { useAddToSilpoCart, useSilpoConnection } from '../hooks/useSilpo';

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

type CartState = 'added' | 'not_added';

/** What goes to the cart for a line: only a ready pick with an amount to buy. A short-stock line
 * (`partial_stock`) is left out: Silpo would refuse the full amount. */
function cartItem(line: ShoppingLine): CartItem | null {
  if (line.status !== 'ok' || !line.product?.product_id || !line.purchase) return null;
  return { product_id: line.product.product_id, quantity: line.purchase.quantity };
}

const SMALL_BUTTON =
  'focus:ring-accent-500 min-h-9 rounded-lg border border-olive-800 px-3 text-sm font-semibold text-olive-800 transition hover:bg-cream-100 focus:ring-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50';

function CartButton({
  state,
  disabled,
  onAdd,
}: {
  state: CartState | undefined;
  disabled: boolean;
  onAdd: () => void;
}) {
  if (state === 'added') {
    return <span className="text-sm font-semibold text-olive-800">✓ У кошику</span>;
  }
  if (state === 'not_added') {
    return <span className="text-accent-600 text-sm font-medium">не додано</span>;
  }
  return (
    <button type="button" onClick={onAdd} disabled={disabled} className={SMALL_BUTTON}>
      У кошик
    </button>
  );
}

function CartNotice({
  pricedIn,
  loggedIn,
  connected,
}: {
  pricedIn: 'your_store' | 'default_store';
  loggedIn: boolean;
  connected: boolean | undefined;
}) {
  const link = 'font-medium underline hover:text-olive-800';
  if (pricedIn === 'your_store') {
    return <p className="text-sm text-olive-800">Ціни й наявність у вашому магазині Сільпо.</p>;
  }
  if (!loggedIn) {
    return (
      <p className="text-sm text-olive-800">
        Ціни орієнтовні.{' '}
        <Link to="/login" className={link}>
          Увійдіть
        </Link>{' '}
        і підключіть Сільпо, щоб бачити ціни свого магазину й класти товари в кошик одним кліком.
      </p>
    );
  }
  if (connected === false) {
    return (
      <p className="text-sm text-olive-800">
        Ціни орієнтовні.{' '}
        <Link to="/profile" className={link}>
          Підключіть Сільпо
        </Link>
        , щоб бачити ціни свого магазину й класти товари в кошик одним кліком.
      </p>
    );
  }
  if (connected) {
    return (
      <p className="text-sm text-olive-800">
        Ваш акаунт Сільпо зараз недоступний для пошуку (наприклад, у ньому не вибрано адресу
        доставки), тому ціни орієнтовні, а додати товари в кошик не вийде.
      </p>
    );
  }
  return null;
}

function CartOutcome({ result }: { result: CartAddResult }) {
  return (
    <div className="bg-cream-100 space-y-1 rounded-xl px-4 py-3 text-sm text-olive-900">
      {result.notes.map((note) => (
        <p key={note}>{note}</p>
      ))}
      {result.checkout_url ? (
        <a
          href={result.checkout_url}
          target="_blank"
          rel="noreferrer"
          className="inline-block font-semibold underline hover:text-olive-800"
        >
          Оформити замовлення в Сільпо →
        </a>
      ) : null}
    </div>
  );
}

function cartItems(lines: ShoppingLine[]): CartItem[] {
  // One entry per product: two ingredients can resolve to the same Silpo product.
  const byId = new Map<string, CartItem>();
  for (const line of lines) {
    const item = cartItem(line);
    if (item && !byId.has(item.product_id)) byId.set(item.product_id, item);
  }
  return [...byId.values()];
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

interface LineCart {
  state: CartState | undefined;
  disabled: boolean;
  onAdd: () => void;
}

function Line({ line, cart }: { line: ShoppingLine; cart: LineCart | null }) {
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
        <span className="flex items-center gap-3">
          {line.purchase ? (
            <span
              className={line.status === 'ok' ? 'font-semibold text-olive-800' : 'text-olive-600'}
            >
              {purchaseText(line.purchase)}
            </span>
          ) : null}
          {cart ? <CartButton {...cart} /> : null}
        </span>
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
  const me = useMe();
  const silpo = useSilpoConnection(!!me.data);
  const addToCart = useAddToSilpoCart();
  const [inCart, setInCart] = useState<Record<string, CartState>>({});
  const [outcome, setOutcome] = useState<CartAddResult | null>(null);

  // Only a list searched in the user's own store holds products their cart accepts.
  const cartReady = data?.priced_in === 'your_store';
  const pending = cartItems(data?.lines ?? []).filter((i) => !inCart[i.product_id]);

  function add(items: CartItem[]) {
    addToCart.mutate(
      { items },
      {
        onSuccess: (result) => {
          setInCart((prev) => {
            const next = { ...prev };
            for (const id of result.added) next[id] = 'added';
            for (const id of result.not_added) next[id] = 'not_added';
            return next;
          });
          setOutcome(result);
        },
      },
    );
  }

  function lineCart(line: ShoppingLine): LineCart | null {
    const item = cartReady ? cartItem(line) : null;
    if (!item) return null;
    return {
      state: inCart[item.product_id],
      disabled: addToCart.isPending,
      onAdd: () => add([item]),
    };
  }

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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <CartNotice
              pricedIn={data.priced_in}
              loggedIn={!!me.data}
              connected={silpo.data?.connected}
            />
            {cartReady && pending.length > 0 ? (
              <button
                type="button"
                onClick={() => add(pending)}
                disabled={addToCart.isPending}
                className="text-cream-50 focus:ring-accent-500 min-h-10 rounded-xl bg-olive-800 px-4 font-semibold transition hover:bg-olive-900 focus:ring-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
              >
                {addToCart.isPending
                  ? 'Додаємо в кошик…'
                  : `Додати все в кошик · ${pending.length}`}
              </button>
            ) : null}
          </div>
          {addToCart.isError ? (
            <p role="alert" className="text-accent-600 text-sm font-medium">
              {addToCart.error.message}
            </p>
          ) : null}
          {outcome ? <CartOutcome result={outcome} /> : null}
          {data.needs_attention > 0 ? (
            <p className="bg-cream-100 rounded-xl px-4 py-3 text-sm text-olive-900">
              Потребують уваги: {data.needs_attention}. Для них нижче показано, що відомо від
              Сільпо.
            </p>
          ) : null}
          <ul className="divide-cream-200 divide-y">
            {data.lines.map((line, idx) => (
              <Line key={`${line.name}-${idx}`} line={line} cart={lineCart(line)} />
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
