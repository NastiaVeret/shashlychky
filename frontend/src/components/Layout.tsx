import { Link, NavLink, useNavigate } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useLogout, useMe } from '../hooks/useAuth';

const NAV_ITEM =
  'focus:ring-accent-500 flex min-h-10 items-center rounded-lg px-3 text-sm font-medium text-olive-900 transition hover:bg-olive-200 focus:ring-2 focus:outline-none aria-[current=page]:bg-olive-200';

function AccountNav() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();

  // Until we know, keep the slot (no layout shift) and do not claim "guest": a logged-in user
  // must not see "Увійти" because /me is pending or failed on a network blip.
  if (me.isPending || me.isError) {
    return <div className="min-h-10" aria-hidden />;
  }

  if (!me.data) {
    return (
      <nav aria-label="Акаунт">
        <NavLink to="/login" className={NAV_ITEM}>
          Увійти
        </NavLink>
      </nav>
    );
  }

  return (
    <nav aria-label="Акаунт" className="flex flex-wrap items-center gap-1">
      <NavLink to="/my-recipes" className={NAV_ITEM}>
        Мої рецепти
      </NavLink>
      <NavLink to="/profile" className={NAV_ITEM}>
        Профіль
      </NavLink>
      <button
        type="button"
        onClick={() => logout.mutate(undefined, { onSettled: () => navigate('/') })}
        disabled={logout.isPending}
        className={`${NAV_ITEM} disabled:opacity-50`}
      >
        Вийти
      </button>
    </nav>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-2 px-4 pt-6 sm:px-6">
        <Link
          to="/"
          className="font-display focus:ring-accent-500 text-2xl font-black tracking-tight text-olive-900 focus:rounded focus:ring-2 focus:outline-none"
        >
          Shashlychky
        </Link>
        <AccountNav />
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
      <footer className="mx-auto w-full max-w-5xl px-4 py-6 text-xs text-olive-800/70 sm:px-6">
        Рецепт генерує модель штучного інтелекту. Перевіряйте алергени та терміни придатності
        самостійно.
      </footer>
    </div>
  );
}
