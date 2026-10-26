import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
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

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
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
