# 6. JavaScript performance (Low-Medium)

These matter in hot paths (render functions of big lists, event handlers firing per frame). Elsewhere, readability wins.

## js-index-maps: `Map` instead of repeated `.find()`

```ts
// Bad: O(n·m)
rows.map((r) => ({ ...r, user: users.find((u) => u.id === r.userId) }));
// Good
const byId = new Map(users.map((u) => [u.id, u]));
rows.map((r) => ({ ...r, user: byId.get(r.userId) }));
```

## js-set-lookup: `Set` for membership

`selected.has(id)` not `selected.includes(id)` when the collection is more than a handful.

## js-single-pass: one loop instead of chained `filter().map().reduce()` on large arrays

Or `flatMap` for map-and-filter in one pass. For small arrays keep the readable chain.

## js-early-return: exit as soon as the answer is known

Including length checks before deep equality: `a.length !== b.length || ...`.

## js-hoist-regexp: regexes and formatters are created once

`const DATE = new Intl.DateTimeFormat('uk-UA', {...})` at module level; `new Intl.*` inside render is one of the most expensive things you can do per row.

## js-cache-storage: read `localStorage`/cookies once

They are synchronous and slow; read into memory, write back on change.

## js-tosorted: non-mutating array methods

`toSorted`, `toReversed`, `with`, `toSpliced` instead of `[...xs].sort(...)`; never `.sort()` on props or state.

## js-min-max-loop: a loop, not `sort()[0]`, for extremes

`Math.max(...xs)` is fine under ~10k elements; above that, a `for` loop (spread hits argument limits).

## js-idle-work: defer non-critical work

Analytics batching, prefetch warming, heavy logging: `requestIdleCallback` (with a `setTimeout` fallback) so it never competes with user input.

## js-cache-property-access: hoist repeated deep reads out of loops

`const items = state.cart.items;` before the loop, not `state.cart.items[i]` inside.
