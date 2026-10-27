---
name: react-best-practices
description: React 19 + TypeScript + Vite performance and correctness guidelines for this frontend - async waterfalls, bundle size, react-query data fetching, re-render optimisation, rendering, JavaScript performance, advanced hooks patterns. Use when writing, reviewing or refactoring components, hooks, data fetching or routing in frontend/, or when asked "why is this slow", "optimise this component", "review the React code".
---

# React best practices (frontend)

Adapted from Vercel's `react-best-practices` skill (MIT, Vercel Engineering), with the Next.js / React Server Components
rules removed because this project is a Vite single-page app using `react-router-dom` and `@tanstack/react-query`.
Project rules in `.claude/rules/frontend.md` win over this skill.

## How to use

1. Writing a component or hook: skim the quick reference; open the category file when the situation matches.
2. Reviewing or profiling: walk the categories top-down. Fix Critical and High before touching Medium.
3. Measure before optimising re-renders: React DevTools Profiler, not intuition. Rules 1 to 3 are worth applying blind; rules 4 to 7 only where profiling or obvious patterns point.

## Quick reference

| # | Category | Priority | File | Rule prefix |
|---|---|---|---|---|
| 1 | Eliminating async waterfalls | Critical | `rules/async-waterfalls.md` | `async-` |
| 2 | Bundle size | Critical | `rules/bundle-size.md` | `bundle-` |
| 3 | Client-side data fetching (react-query) | High | `rules/data-fetching.md` | `fetch-` |
| 4 | Re-render optimisation | Medium | `rules/rerender.md` | `rerender-` |
| 5 | Rendering performance | Medium | `rules/rendering.md` | `render-` |
| 6 | JavaScript performance | Low-Medium | `rules/js-performance.md` | `js-` |
| 7 | Advanced hook patterns | Low | `rules/advanced.md` | `advanced-` |

### The ten rules worth memorizing

1. Independent requests start together (`useQueries`, `Promise.all`), never one after another.
2. Fetch at the route level and let children read from the cache; do not nest fetch-inside-fetch components.
3. Route pages are `React.lazy` + `Suspense`; heavy libraries load on demand.
4. Import from the specific module, not a barrel `index.ts`, when the barrel pulls in heavy code.
5. All server data goes through react-query with array keys and explicit `staleTime`; mutations invalidate exactly the keys they affect.
6. Derive state during render; do not copy props into state and sync them with effects.
7. Effects are for synchronising with external systems, not for reacting to user events. Event logic lives in handlers.
8. Never define a component inside another component; never pass a new object/array literal as a default prop.
9. Memoise the expensive, not the trivial: `useMemo` for real computation and referential stability that a memoised child needs, not for `a + b`.
10. Lists render stable `key`s from data ids; long lists are virtualised or `content-visibility: auto`.
