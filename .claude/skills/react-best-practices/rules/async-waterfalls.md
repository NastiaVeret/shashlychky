# 1. Eliminating async waterfalls (Critical)

A waterfall is request B waiting for request A when it did not need to. Each one adds a full network round-trip to the page.

## async-parallel: independent queries start together

```tsx
// Bad: orders start only after user resolves
const user = useQuery({ queryKey: ['user', id], queryFn: () => getUser(id) });
const orders = useQuery({
  queryKey: ['orders', id],
  queryFn: () => getOrders(id),
  enabled: !!user.data,          // artificial dependency
});

// Good
const [user, orders] = useQueries({
  queries: [
    { queryKey: ['user', id], queryFn: () => getUser(id) },
    { queryKey: ['orders', id], queryFn: () => getOrders(id) },
  ],
});
```

`enabled:` is for real dependencies (you do not know the id yet), not for sequencing.

## async-promise-all: inside one function, `Promise.all`

```ts
// Bad
const a = await getA(); const b = await getB();
// Good
const [a, b] = await Promise.all([getA(), getB()]);
```

Use `Promise.allSettled` when partial failure is acceptable and you will render what arrived.

## async-hoist-fetch: fetch where the data is first known, not where it is first rendered

Nested components that each `useQuery` for their own data create a waterfall by component depth: parent renders → child mounts → child fetches. Start the queries in the route page (or prefetch them in a router `loader`) and let children call the same `useQuery` with the same key; they get the cached result.

## async-prefetch-on-intent: prefetch before navigation

```tsx
const qc = useQueryClient();
<Link to={`/orders/${id}`} onMouseEnter={() => qc.prefetchQuery({ queryKey: ['orders', id], queryFn: () => getOrder(id) })}>
```

Hover/focus happens 100 to 300 ms before the click; that is a free head start.

## async-defer-await: await only on the path that needs it

```ts
// Bad: both awaited even when flag is false
const [flags, heavy] = await Promise.all([getFlags(), getHeavy()]);
if (!flags.enabled) return basic();
// Good
const flags = await getFlags();
if (!flags.enabled) return basic();
const heavy = await getHeavy();
```

Cheap synchronous checks go before any await.

## async-suspense-boundaries: show the frame, stream the slow parts

Wrap the slow widget, not the whole page, in `<Suspense fallback>` (`useSuspenseQuery`). The layout, navigation and fast data render immediately; the slow part fills in. One boundary per independent chunk of slow content, not one per component.
