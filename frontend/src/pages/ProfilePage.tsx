import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import type { Diet, Equipment, UserProfile } from '../api/profile';
import { ProductInput } from '../components/ProductInput';
import { useDeleteAccount, useMe } from '../hooks/useAuth';
import { useProfile, useUpdateProfile } from '../hooks/useProfile';

const DIETS: { value: Diet; label: string }[] = [
  { value: 'vegetarian', label: 'Вегетаріанство' },
  { value: 'vegan', label: 'Веганство' },
  { value: 'pescatarian', label: 'Пескетаріанство' },
  { value: 'gluten_free', label: 'Без глютену' },
  { value: 'lactose_free', label: 'Без лактози' },
  { value: 'halal', label: 'Халяль' },
  { value: 'fasting', label: 'Піст' },
];

const EQUIPMENT: { value: Equipment; label: string }[] = [
  { value: 'stovetop', label: 'Плита' },
  { value: 'oven', label: 'Духовка' },
  { value: 'microwave', label: 'Мікрохвильовка' },
  { value: 'multicooker', label: 'Мультиварка' },
  { value: 'air_fryer', label: 'Аерогриль' },
  { value: 'blender', label: 'Блендер' },
];

const SERVINGS = [1, 2, 4, 6] as const;

const TOGGLE =
  'bg-cream-50 focus:ring-accent-500 aria-pressed:text-cream-50 min-h-10 rounded-full border-2 border-olive-200 px-4 text-sm font-semibold transition hover:border-olive-400 focus:ring-2 focus:outline-none aria-pressed:border-olive-800 aria-pressed:bg-olive-800';
const SECTION = 'rounded-card bg-cream-100 shadow-card space-y-6 p-5 sm:p-8';

function toggled<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

function ProfileForm({ initial }: { initial: UserProfile }) {
  // Local draft, saved explicitly: the server normalizes lists, so the draft is replaced on save.
  const [draft, setDraft] = useState(initial);
  const update = useUpdateProfile();

  const change = (patch: Partial<UserProfile>) => {
    setDraft((d) => ({ ...d, ...patch }));
    update.reset();
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    update.mutate(draft, { onSuccess: setDraft });
  };

  return (
    <form onSubmit={onSubmit} aria-busy={update.isPending} className={SECTION}>
      <div>
        <ProductInput
          id="allergies"
          label="Алергени"
          placeholder="Наприклад: арахіс, молоко"
          suggestions={['арахіс', 'горіхи', 'молоко', 'яйця', 'глютен', 'риба', 'кунжут', 'мед']}
          products={draft.allergies ?? []}
          onChange={(allergies) => change({ allergies })}
          max={20}
          disabled={update.isPending}
        />
        <p className="mt-2 text-xs text-olive-800/80">
          Їх не буде в жодному рецепті: ми перевіряємо відповідь моделі ще раз на сервері.
        </p>
      </div>

      <fieldset>
        <legend className="mb-2 text-sm font-semibold text-olive-800">Харчування</legend>
        <div className="flex flex-wrap gap-2">
          {DIETS.map((d) => (
            <button
              key={d.value}
              type="button"
              aria-pressed={draft.diets?.includes(d.value) ?? false}
              onClick={() => change({ diets: toggled(draft.diets ?? [], d.value) })}
              className={TOGGLE}
            >
              {d.label}
            </button>
          ))}
        </div>
      </fieldset>

      <ProductInput
        id="disliked"
        label="Не їм"
        placeholder="Наприклад: цибуля, гриби"
        suggestions={['цибуля', 'гриби', 'печінка', 'броколі', 'кінза', 'баклажани']}
        products={draft.disliked ?? []}
        onChange={(disliked) => change({ disliked })}
        max={30}
        disabled={update.isPending}
      />

      <fieldset>
        <legend className="mb-2 text-sm font-semibold text-olive-800">Кухонна техніка</legend>
        <div className="flex flex-wrap gap-2">
          {EQUIPMENT.map((eq) => (
            <button
              key={eq.value}
              type="button"
              aria-pressed={draft.equipment?.includes(eq.value) ?? false}
              onClick={() => change({ equipment: toggled(draft.equipment ?? [], eq.value) })}
              className={TOGGLE}
            >
              {eq.label}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-olive-800/80">
          Нічого не вибрано: вважаємо, що кухня звичайна.
        </p>
      </fieldset>

      <fieldset>
        <legend className="mb-2 text-sm font-semibold text-olive-800">Порцій зазвичай</legend>
        <div className="flex gap-2">
          {SERVINGS.map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={(draft.default_servings ?? 2) === n}
              onClick={() => change({ default_servings: n })}
              className={`${TOGGLE} flex-1`}
            >
              {n}
            </button>
          ))}
        </div>
      </fieldset>

      <div>
        <ProductInput
          id="pantry"
          label="Завжди є вдома"
          placeholder="Наприклад: рис, олія, часник"
          suggestions={['рис', 'гречка', 'макарони', 'олія', 'борошно', 'цукор', 'часник']}
          products={draft.pantry ?? []}
          onChange={(pantry) => change({ pantry })}
          max={50}
          disabled={update.isPending}
        />
        <p className="mt-2 text-xs text-olive-800/80">
          Ці продукти не треба вписувати щоразу: модель знатиме, що вони є.
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <button
          type="submit"
          disabled={update.isPending}
          className="bg-accent-500 text-cream-50 hover:bg-accent-600 focus:ring-accent-500/40 rounded-xl px-6 py-3 text-base font-bold shadow-sm transition focus:ring-4 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          {update.isPending ? 'Зберігаємо…' : 'Зберегти профіль'}
        </button>
        {update.isSuccess ? (
          <p role="status" className="text-sm font-medium text-olive-800">
            Збережено. Наступні рецепти врахують профіль.
          </p>
        ) : null}
        {update.isError ? (
          <p role="alert" className="text-accent-600 text-sm font-medium">
            {update.error.message}
          </p>
        ) : null}
      </div>
    </form>
  );
}

function DeleteAccount() {
  const [confirming, setConfirming] = useState(false);
  const remove = useDeleteAccount();
  const navigate = useNavigate();

  return (
    <section className={SECTION} aria-labelledby="delete-heading">
      <h2 id="delete-heading" className="font-display text-xl font-bold">
        Видалити мої дані
      </h2>
      <p className="text-sm text-olive-800">
        Буде видалено акаунт, профіль і всі ваші рецепти, разом із посиланнями на них. Скасувати це
        не можна.
      </p>
      {confirming ? (
        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            onClick={() => remove.mutate(undefined, { onSuccess: () => navigate('/') })}
            disabled={remove.isPending}
            className="bg-accent-600 text-cream-50 focus:ring-accent-500/40 hover:bg-accent-500 min-h-10 rounded-xl px-5 font-bold transition focus:ring-4 focus:outline-none disabled:opacity-50"
          >
            {remove.isPending ? 'Видаляємо…' : 'Так, видалити назавжди'}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={remove.isPending}
            className="focus:ring-accent-500 min-h-10 rounded-xl border-2 border-olive-200 px-5 font-semibold transition hover:border-olive-400 focus:ring-2 focus:outline-none"
          >
            Скасувати
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="text-accent-600 focus:ring-accent-500 border-accent-500/40 hover:border-accent-500 min-h-10 rounded-xl border-2 px-5 font-semibold transition focus:ring-2 focus:outline-none"
        >
          Видалити акаунт
        </button>
      )}
      {remove.isError ? (
        <p role="alert" className="text-accent-600 text-sm font-medium">
          {remove.error.message}
        </p>
      ) : null}
    </section>
  );
}

export function ProfilePage() {
  const me = useMe();
  const profile = useProfile(!!me.data);

  if (me.isPending) return null;
  if (!me.data) return <Navigate to="/login" replace />;

  return (
    <div className="space-y-6 pt-8">
      <div>
        <h1 className="font-display text-4xl font-black text-olive-900">Профіль</h1>
        <p className="mt-2 text-olive-900/85">{me.data.email}</p>
      </div>
      {profile.isPending ? (
        <div role="status" className="rounded-card bg-cream-50/70 animate-pulse p-8 text-center">
          Завантажуємо профіль…
        </div>
      ) : null}
      {profile.isError ? (
        <p role="alert" className="rounded-card bg-cream-50 text-accent-600 p-6 font-medium">
          {profile.error.message}
        </p>
      ) : null}
      {profile.data ? <ProfileForm initial={profile.data} /> : null}
      <DeleteAccount />
    </div>
  );
}
