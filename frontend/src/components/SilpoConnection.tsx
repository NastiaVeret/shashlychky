import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useConnectSilpo, useDisconnectSilpo, useSilpoConnection } from '../hooks/useSilpo';

const DATE = new Intl.DateTimeFormat('uk-UA', { day: 'numeric', month: 'long', year: 'numeric' });

// The backend callback redirects to /profile?silpo=<outcome> after the login on Silpo's site.
const OUTCOMES = {
  connected: { text: 'Акаунт Сільпо підключено', failed: false },
  denied: { text: 'Ви скасували вхід у Сільпо', failed: true },
  error: { text: 'Не вдалося підключити Сільпо. Спробуйте ще раз.', failed: true },
} as const;
type Outcome = keyof typeof OUTCOMES;

const isOutcome = (value: string | null): value is Outcome =>
  value !== null && Object.hasOwn(OUTCOMES, value);

/** Reads `?silpo=` once, then drops it from the URL without adding a history entry. */
function useSilpoOutcome() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [outcome, setOutcome] = useState<Outcome | null>(() => {
    const value = searchParams.get('silpo');
    return isOutcome(value) ? value : null;
  });

  useEffect(() => {
    if (!searchParams.has('silpo')) return;
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.delete('silpo');
        return next;
      },
      { replace: true },
    );
  }, [searchParams, setSearchParams]);

  return [outcome, () => setOutcome(null)] as const;
}

export function SilpoConnection() {
  const connection = useSilpoConnection(true);
  const connect = useConnectSilpo();
  const disconnect = useDisconnectSilpo();
  const [outcome, clearOutcome] = useSilpoOutcome();
  // After success the browser is already leaving for Silpo: keep the button busy until it does.
  const redirecting = connect.isPending || connect.isSuccess;
  const busy = redirecting || disconnect.isPending;

  const onConnect = () => {
    clearOutcome();
    disconnect.reset();
    connect.mutate();
  };

  const onDisconnect = () => {
    clearOutcome();
    connect.reset();
    disconnect.mutate();
  };

  const connectedAt = connection.data?.connected_at;
  const error = connect.error ?? disconnect.error;

  return (
    <section
      className="rounded-card bg-cream-100 shadow-card space-y-4 p-5 sm:p-8"
      aria-labelledby="silpo-heading"
      aria-busy={busy}
    >
      <h2 id="silpo-heading" className="font-display text-xl font-bold">
        Сільпо
      </h2>

      {outcome ? (
        <p
          role={OUTCOMES[outcome].failed ? 'alert' : 'status'}
          className={`text-sm font-medium ${OUTCOMES[outcome].failed ? 'text-accent-600' : 'text-olive-800'}`}
        >
          {OUTCOMES[outcome].text}
        </p>
      ) : null}

      {connection.isPending ? (
        <p role="status" className="animate-pulse text-sm text-olive-800">
          Перевіряємо підключення…
        </p>
      ) : null}
      {connection.isError ? (
        <p role="alert" className="text-accent-600 text-sm font-medium">
          {connection.error.message}
        </p>
      ) : null}

      {connection.data?.connected ? (
        <>
          <div>
            <p className="font-semibold text-olive-900">Акаунт Сільпо підключено</p>
            {connectedAt ? (
              <p className="mt-1 text-sm text-olive-800">
                Підключено {DATE.format(new Date(connectedAt))}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onDisconnect}
            disabled={busy}
            className="focus:ring-accent-500 min-h-10 rounded-xl border-2 border-olive-200 px-5 font-semibold transition hover:border-olive-400 focus:ring-2 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {disconnect.isPending ? 'Відключаємо…' : 'Відключити'}
          </button>
        </>
      ) : null}

      {connection.data && !connection.data.connected ? (
        <>
          <p className="max-w-2xl text-sm text-olive-800">
            Підключіть акаунт Сільпо, щоб застосунок міг працювати з вашим кошиком і вподобаннями.
          </p>
          <button
            type="button"
            onClick={onConnect}
            disabled={busy}
            className="bg-accent-500 text-cream-50 hover:bg-accent-600 focus:ring-accent-500/40 min-h-10 rounded-xl px-6 py-3 text-base font-bold shadow-sm transition focus:ring-4 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {redirecting ? 'Переходимо до Сільпо…' : 'Підключити Сільпо'}
          </button>
        </>
      ) : null}

      {error ? (
        <p role="alert" className="text-accent-600 text-sm font-medium">
          {error.message}
        </p>
      ) : null}
    </section>
  );
}
