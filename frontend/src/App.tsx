import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { ApiError } from './api/client';
import { Layout } from './components/Layout';
import { onLoggedOut } from './hooks/useAuth';
import { HomePage } from './pages/HomePage';

const RecipePage = lazy(() =>
  import('./pages/RecipePage').then((m) => ({ default: m.RecipePage })),
);
const AuthPage = lazy(() => import('./pages/AuthPage').then((m) => ({ default: m.AuthPage })));
const ProfilePage = lazy(() =>
  import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })),
);
const MyRecipesPage = lazy(() =>
  import('./pages/MyRecipesPage').then((m) => ({ default: m.MyRecipesPage })),
);

const isUnauthorized = (err: unknown) => err instanceof ApiError && err.status === 401;
const isClientError = (err: unknown) => err instanceof ApiError && err.status < 500;

// A 401 from any request (expired or revoked session) drops the cached user and everything
// personal, so the header and the guarded pages react at once. `getMe` itself maps 401 to
// `null`, so it never reaches these handlers. 4xx answers are final: no retries.
const queryClient: QueryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (err) => {
      if (isUnauthorized(err)) onLoggedOut(queryClient);
    },
  }),
  mutationCache: new MutationCache({
    onError: (err) => {
      if (isUnauthorized(err)) onLoggedOut(queryClient);
    },
  }),
  defaultOptions: {
    queries: {
      retry: (count, err) => count < 1 && !isClientError(err),
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Suspense fallback={null}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/recipes/:id" element={<RecipePage />} />
              <Route path="/login" element={<AuthPage />} />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/my-recipes" element={<MyRecipesPage />} />
            </Routes>
          </Suspense>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
