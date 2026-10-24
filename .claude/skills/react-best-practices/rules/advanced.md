# 7. Advanced hook patterns (Low)

Use these when the simpler rules do not fit; each solves a specific problem.

## advanced-effect-event: `useEffectEvent` for "latest callback" inside effects

```tsx
const onTick = useEffectEvent(() => report(count));   // always sees latest count
useEffect(() => {
  const id = setInterval(onTick, 1000);
  return () => clearInterval(id);
}, []);                                                // effect does not restart on count changes
```

Never list an effect event in the dependency array.

## advanced-handler-ref: store handlers in refs when a stable identity is required

For imperative APIs (third-party widgets, `addEventListener` set up once): keep `const handlerRef = useRef(onChange); handlerRef.current = onChange;` and call `handlerRef.current()` inside the stable listener.

## advanced-init-once: app-level initialisation happens once, not per mount

Analytics init, auth listeners, global error handlers: module-level guard or in `main.tsx`, not in a component effect that runs again under StrictMode or on remount.

## advanced-external-store: `useSyncExternalStore` for non-React state

Browser APIs (`matchMedia`, `navigator.onLine`), tiny custom stores. Correct tearing-free subscription with no effects and no stale first render.

## advanced-abort: cancel what the user no longer needs

react-query passes an `AbortSignal` to `queryFn` (`({ signal }) => apiFetch(url, { signal })`). Forward it so navigating away cancels in-flight requests.

## advanced-error-boundaries: fail small

An `ErrorBoundary` around each independent widget, with a retry that calls `queryClient.resetQueries`. One crashed chart must not blank the page.

## advanced-strict-mode: keep StrictMode on

It double-invokes renders and effects in development to surface exactly the bugs this skill describes. Fix the code, do not remove StrictMode.
