import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useLogin, useMe, useRegister } from '../hooks/useAuth';

type Mode = 'login' | 'register';

const MODES: { value: Mode; label: string }[] = [
  { value: 'login', label: 'Вхід' },
  { value: 'register', label: 'Реєстрація' },
];

const INPUT =
  'bg-cream-50 focus:border-accent-500 focus:ring-accent-500/20 w-full rounded-xl border-2 border-olive-200 px-3 py-2 transition outline-none placeholder:text-olive-600/60 focus:ring-4';

export function AuthPage() {
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const me = useMe();
  const login = useLogin();
  const register = useRegister();
  const navigate = useNavigate();
  const mutation = mode === 'login' ? login : register;

  // Already logged in and not in the middle of this form's own success redirect.
  if (me.data && mutation.isIdle) return <Navigate to="/" replace />;

  const switchMode = (next: Mode) => {
    setMode(next);
    login.reset();
    register.reset();
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    mutation.mutate({ email, password }, { onSuccess: () => navigate('/') });
  };

  return (
    <div className="mx-auto max-w-md space-y-6 pt-8 sm:pt-14">
      <h1 className="font-display text-4xl font-black text-olive-900">
        {mode === 'login' ? 'Вхід' : 'Новий акаунт'}
      </h1>

      <form
        onSubmit={onSubmit}
        aria-busy={mutation.isPending}
        className="rounded-card bg-cream-100 shadow-card space-y-5 p-5 sm:p-8"
      >
        <div className="flex gap-2">
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => switchMode(m.value)}
              aria-pressed={mode === m.value}
              className="bg-cream-50 focus:ring-accent-500 aria-pressed:text-cream-50 min-h-10 flex-1 rounded-xl border-2 border-olive-200 font-semibold transition hover:border-olive-400 focus:ring-2 focus:outline-none aria-pressed:border-olive-800 aria-pressed:bg-olive-800"
            >
              {m.label}
            </button>
          ))}
        </div>

        <div>
          <label htmlFor="email" className="mb-2 block text-sm font-semibold text-olive-800">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            maxLength={254}
            autoComplete="email"
            className={INPUT}
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-2 block text-sm font-semibold text-olive-800">
            Пароль
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={mode === 'register' ? 8 : undefined}
            maxLength={128}
            autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
            aria-describedby={mode === 'register' ? 'password-hint' : undefined}
            className={INPUT}
          />
          {mode === 'register' ? (
            <p id="password-hint" className="mt-2 text-xs text-olive-800/80">
              Щонайменше 8 символів. Відновлення пароля поки немає, тож збережіть його в менеджері
              паролів.
            </p>
          ) : null}
        </div>

        <button
          type="submit"
          disabled={mutation.isPending}
          className="bg-accent-500 text-cream-50 hover:bg-accent-600 focus:ring-accent-500/40 w-full rounded-xl px-6 py-3 text-base font-bold shadow-sm transition focus:ring-4 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
        >
          {mutation.isPending ? 'Зачекайте…' : mode === 'login' ? 'Увійти' : 'Створити акаунт'}
        </button>

        {mutation.isError ? (
          <p role="alert" className="text-accent-600 text-sm font-medium">
            {mutation.error.message}
          </p>
        ) : null}
      </form>
    </div>
  );
}
