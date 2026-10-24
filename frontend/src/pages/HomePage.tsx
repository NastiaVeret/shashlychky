import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/client';

export function HomePage() {
  const { data, isPending, error } = useQuery({ queryKey: ['health'], queryFn: getHealth });

  return (
    <main>
      <h1>Шашлички</h1>
      {isPending && <p>Перевіряю бекенд…</p>}
      {error && <p>Бекенд недоступний: {error.message}</p>}
      {data && (
        <p>
          Бекенд: {data.status}, версія {data.version}
        </p>
      )}
    </main>
  );
}
