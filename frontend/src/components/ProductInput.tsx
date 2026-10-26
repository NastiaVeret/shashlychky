import { useState, type KeyboardEvent } from 'react';

interface Props {
  products: string[];
  onChange: (products: string[]) => void;
  max?: number;
  disabled?: boolean;
  /** Defaults fit the recipe form; the profile page reuses the input for its product lists. */
  id?: string;
  label?: string;
  placeholder?: string;
  suggestions?: readonly string[];
}

const SUGGESTIONS = ['яйця', 'картопля', 'курка', 'помідори', 'сир', 'рис', 'цибуля', 'гриби'];

/** Chip input: type a product, press Enter or comma to add it. */
export function ProductInput({
  products,
  onChange,
  max = 30,
  disabled,
  id = 'product-input',
  label = 'Що є вдома?',
  placeholder = 'Наприклад: яйця, картопля, цибуля',
  suggestions = SUGGESTIONS,
}: Props) {
  const [draft, setDraft] = useState('');

  const add = (raw: string) => {
    const name = raw.trim().replace(/,+$/, '').trim();
    if (!name) return;
    const exists = products.some((p) => p.toLocaleLowerCase('uk') === name.toLocaleLowerCase('uk'));
    if (!exists && products.length < max) onChange([...products, name]);
    setDraft('');
  };

  const remove = (name: string) => onChange(products.filter((p) => p !== name));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      add(draft);
    } else if (e.key === 'Backspace' && draft === '' && products.length > 0) {
      remove(products[products.length - 1]);
    }
  };

  const unusedSuggestions = suggestions
    .filter((s) => !products.some((p) => p.toLocaleLowerCase('uk') === s))
    .slice(0, 6);

  return (
    <div>
      <label htmlFor={id} className="mb-2 block text-sm font-semibold text-olive-800">
        {label}
      </label>
      <div
        className="rounded-card bg-cream-50 focus-within:border-accent-500 focus-within:ring-accent-500/20 flex min-h-14 flex-wrap items-center gap-2 border-2 border-olive-200 px-3 py-2 transition focus-within:ring-4"
        onClick={() => document.getElementById(id)?.focus()}
      >
        {products.map((p) => (
          <span
            key={p}
            className="inline-flex items-center gap-1 rounded-full bg-olive-100 py-1 pr-1 pl-3 text-sm font-medium text-olive-900"
          >
            {p}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                remove(p);
              }}
              disabled={disabled}
              aria-label={`Прибрати ${p}`}
              className="focus:ring-accent-500 flex size-6 items-center justify-center rounded-full text-olive-600 hover:bg-olive-200 hover:text-olive-900 focus:ring-2 focus:outline-none"
            >
              ×
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => add(draft)}
          disabled={disabled || products.length >= max}
          placeholder={products.length === 0 ? placeholder : 'Додати ще…'}
          autoComplete="off"
          className="min-w-40 flex-1 bg-transparent py-1 text-base outline-none placeholder:text-olive-600/60"
        />
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-olive-800/80">
        <span>Enter або кома додає продукт</span>
        <span>
          {products.length}/{max}
        </span>
      </div>
      {unusedSuggestions.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {unusedSuggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              disabled={disabled}
              className="focus:ring-accent-500 rounded-full border border-olive-800/20 px-3 py-1 text-sm text-olive-900 transition hover:border-olive-800/50 hover:bg-olive-200 focus:ring-2 focus:outline-none"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
