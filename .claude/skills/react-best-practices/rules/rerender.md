# 4. Re-render optimisation (Medium)

Re-renders are cheap until they are not. Profile first; then apply the rule that matches.

## rerender-derive-in-render: compute derived values during render

```tsx
// Bad: a second render and a stale window on every change
const [total, setTotal] = useState(0);
useEffect(() => setTotal(sum(items)), [items]);
// Good
const total = sum(items);                    // or useMemo if sum is expensive
```

Copying props into state and syncing with effects is the most common React bug.

## rerender-no-nested-components: never define a component inside a component

```tsx
// Bad: a new component type every render, remounts children, loses state and focus
function List({ items }) {
  const Row = ({ item }) => <li>{item.name}</li>;
  ...
}
```

Hoist it to module level and pass props.

## rerender-stable-defaults: non-primitive defaults live outside the component

```tsx
const EMPTY: Item[] = [];
function List({ items = EMPTY }) { ... }     // not items = []
```

An inline `[]` or `{}` default is a new reference every render and defeats every `memo` below it.

## rerender-memo-expensive-only: `useMemo`/`useCallback` where they pay

Yes: heavy computation (sorting/filtering thousands of rows), values passed to memoised children or used as effect dependencies.
No: `a + b`, string concatenation, a callback passed to a plain DOM element. The memo bookkeeping costs more than the expression.

## rerender-narrow-deps: depend on primitives

```ts
useEffect(() => { track(user.id); }, [user.id]);   // not [user]
```

Objects change identity on every fetch; ids do not.

## rerender-events-not-effects: user interactions belong in handlers

An effect that runs "when `submitted` becomes true" to send a request is an event handler in disguise. Call the mutation in `onSubmit`.

## rerender-functional-setstate: updater form when the next value depends on the previous

`setCount((c) => c + 1)` avoids stale closures and removes `count` from dependency arrays.

## rerender-lazy-init: expensive initial state via function

`useState(() => parse(bigBlob))`, not `useState(parse(bigBlob))` which runs on every render.

## rerender-transitions: non-urgent updates in `startTransition`

Filtering a large list as the user types: keep the input urgent, wrap the list state update in `startTransition` (or use `useDeferredValue(query)` for the expensive consumer). The input never stutters.

## rerender-split-hooks: independent computations in independent hooks

One `useMemo` that computes three unrelated things re-runs all three when any input changes. Split it.

## rerender-ref-for-transient: `useRef` for values that change often but never render

Mouse positions, timers, latest-callback refs, "has mounted" flags.

## rerender-extract-memoised-child: isolate the hot path

If one branch of a component is expensive and its inputs rarely change, move it into a `memo()` child with narrow props. The parent can re-render freely; the child skips.

## rerender-subscribe-derived: subscribe to booleans, not raw values

`useIsMobile()` returning a boolean re-renders twice per session; `useWindowWidth()` re-renders on every pixel.
