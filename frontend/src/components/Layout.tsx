import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="mx-auto w-full max-w-5xl px-4 pt-6 sm:px-6">
        <Link
          to="/"
          className="font-display focus:ring-accent-500 text-2xl font-black tracking-tight text-olive-900 focus:rounded focus:ring-2 focus:outline-none"
        >
          Shashlychky
        </Link>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 pb-16 sm:px-6">{children}</main>
      <footer className="mx-auto w-full max-w-5xl px-4 py-6 text-xs text-olive-800/70 sm:px-6">
        Рецепт генерує модель штучного інтелекту. Перевіряйте алергени та терміни придатності
        самостійно.
      </footer>
    </div>
  );
}
