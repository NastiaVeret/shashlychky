# 3. Client-side data fetching with react-query (High)

All server state lives in `@tanstack/react-query`; components never hold copies of server data in `useState`.

## fetch-keys: keys are arrays, shaped resource → id → params

```ts
['orders']                       // list
['orders', id]                   // one
['orders', { status, page }]     // filtered list
```

Centralise them in `src/api/<resource>.ts` as a `keys` object so invalidation never typos a string.

## fetch-stale-time: set `staleTime` on purpose

Default `staleTime: 0` refetches on every mount and window focus. Reference data (categories, settings) gets minutes; live data gets seconds; set it per query or in `QueryClient` defaults. Decide, do not inherit.

## fetch-invalidate-precisely: mutations invalidate what they changed

```ts
useMutation({
  mutationFn: createOrder,
  onSuccess: () => qc.invalidateQueries({ queryKey: ['orders'] }),   // list and every ['orders', id]
});
```

Not `qc.invalidateQueries()` for everything, and not a manual refetch in the component.

## fetch-optimistic: optimistic updates for instant UI, with rollback

`onMutate` sets the cache, `onError` restores the snapshot, `onSettled` invalidates. Use for toggles and small edits where latency is visible; skip for creates with server-generated data.

## fetch-select: narrow what a component subscribes to

```ts
const count = useQuery({ queryKey: ['orders'], queryFn: getOrders, select: (o) => o.length });
```

With `select`, the component re-renders only when the selected value changes.

## fetch-no-effect-fetching: no `useEffect` + `fetch` + `setState`

That pattern lacks caching, deduplication, cancellation, retries and race-condition handling; react-query has all of them. The only `fetch` calls in the codebase are inside `src/api/`.

## fetch-dedupe-listeners: one global listener, many consumers

Window `resize`, `scroll`, `online`, `visibilitychange`: subscribe once in a small store or `useSyncExternalStore` and let components read derived booleans (`isMobile`), instead of each component adding its own listener.

## fetch-passive-listeners: scroll and touch listeners are passive

`addEventListener('scroll', fn, { passive: true })` unless you call `preventDefault()`; otherwise the browser must wait for your handler before scrolling.

## fetch-local-storage: version and minimise what you persist

Key with a version (`'shashlychky:v1:filters'`), store only what is needed, wrap every read/write in try/catch (private mode, quota), and never store server data that react-query already caches.
