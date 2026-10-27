---
paths:
  - "frontend/**"
---

# Frontend (React + TypeScript + Vite)

## Layout

```
src/main.tsx            entry point
src/App.tsx             providers (QueryClient, Router) and routes
src/api/client.ts       apiFetch, ApiError, base URL
src/api/schema.d.ts     GENERATED from the backend OpenAPI schema (`make types`); do not edit
src/api/<resource>.ts   request functions; types are aliases into schema.d.ts (`components['schemas'][...]`)
src/pages/              route pages, one page = one file <Name>Page.tsx
src/components/         reusable components (create when needed)
src/hooks/              custom hooks, incl. useQuery/useMutation wrappers
src/index.css           the only stylesheet: Tailwind import + @theme design tokens
```

## Rules

- Function components only, named exports: `export function HomePage()`.
- Backend data only via `@tanstack/react-query` and functions from `src/api/`. No `fetch`/`axios` in components.
- Query keys are arrays, first element = resource: `['orders']`, `['orders', id]`.
- API types are never hand-written: alias them from the generated `schema.d.ts` (`type RecipeRead = components['schemas']['RecipeRead']`). If a field is missing, the backend schema changes first, then `make types`.
- `any` is forbidden. Unknown shape: `unknown` plus narrowing.
- `erasableSyntaxOnly` is on: no `enum`, no constructor parameter properties, no `namespace`. Use an `as const` object or a union of literals instead of enum.
- Styles: Tailwind CSS v4 utilities only (see the `tailwind` skill). Design tokens live in `src/index.css` `@theme`; no other CSS files, no inline styles, no CSS-in-JS. Run `npm run format` so classes are sorted.
- UI text is in Ukrainian. Keep it as plain strings in JSX; i18n is not needed yet.
- Environment variables only with the `VITE_` prefix, read via `import.meta.env`. No secrets in the frontend.
- API calls use relative paths (`/api/v1/...`). In production Firebase Hosting rewrites `/api/**` to the Cloud Run backend (`firebase.json`); do not hardcode backend URLs.
- `firebase.json` is deployment config: do not change it without discussing with the team.

## Pre-commit check

```bash
npm run format && npm run lint && npm run build
```
