# 2. Bundle size (Critical)

Every kilobyte of JavaScript is parsed and executed on the user's phone before they can interact. Measure with `npx vite-bundle-visualizer` or `npm run build` output.

## bundle-route-splitting: every route page is lazy

```tsx
// App.tsx
const OrdersPage = lazy(() => import('./pages/OrdersPage'));
<Suspense fallback={<PageSkeleton />}>
  <Routes>
    <Route path="/orders" element={<OrdersPage />} />
  </Routes>
</Suspense>
```

`HomePage` may stay eager; everything else is a separate chunk.

## bundle-dynamic-heavy: heavy components load when used

Charts, editors, maps, PDF viewers, date pickers: `lazy(() => import(...))` at the place of use, with a fallback the size of the final component (no layout jump).

## bundle-conditional-modules: load code only when the feature activates

```ts
async function exportCsv(rows: Row[]) {
  const { unparse } = await import('papaparse');   // loaded on first click, not on page load
  download(unparse(rows));
}
```

## bundle-no-barrels: import the module, not the barrel

```ts
// Bad: pulls the whole icon set into the chunk if the barrel is not tree-shakeable
import { Trash } from 'some-icons';
// Good
import Trash from 'some-icons/Trash';
```

Our own `src/api/index.ts`-style barrels are fine (tiny), but do not create barrels that re-export page components.

## bundle-static-paths: dynamic imports must be analysable

```ts
// Bad: Vite cannot know which files to bundle
import(`./locales/${lang}.json`);
// Good: explicit map
const locales = { uk: () => import('./locales/uk.json'), en: () => import('./locales/en.json') };
```

## bundle-defer-third-party: analytics and widgets after first paint

Load tracking, chat widgets and similar scripts after the app has rendered (`useEffect` in the root with `requestIdleCallback`, or a `<script defer>` in `index.html`). They are never on the critical path.

## bundle-check-dependencies: a dependency costs more than it looks

Before `npm install`: check size on bundlephobia, check whether the platform already does it (`Intl.DateTimeFormat`, `Intl.NumberFormat`, `structuredClone`, `Array.prototype.at`), and prefer libraries with ESM and tree-shaking. Per project rules, new dependencies need a team discussion.
