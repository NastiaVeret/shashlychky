---
name: new-page
description: Create a new React page following project conventions - component in src/pages, route in App.tsx, data via react-query and src/api. Use when asked to "add a page", "new screen", "route /...".
argument-hint: <PageName> <route-path> [what it shows]
---

# New page: $ARGUMENTS

Style reference: `frontend/src/pages/HomePage.tsx` and `frontend/src/api/client.ts`. Read them first.

## Steps

1. **Component.** `frontend/src/pages/<Name>Page.tsx`, named export `export function <Name>Page()`.
   Data only via `useQuery`/`useMutation` and functions from `src/api/`. Handle three states: `isPending`, `error`, data.
   UI text in Ukrainian.
2. **API.** If the request functions do not exist yet, add them to `frontend/src/api/<resource>.ts` via `apiFetch`,
   with TS interfaces matching the backend Pydantic models. Confirm the endpoint actually exists in `backend/app/api/v1/`;
   if not, tell the user and suggest `/new-endpoint`.
3. **Route.** Add `<Route path="..." element={<<Name>Page />} />` to `frontend/src/App.tsx`.
   Use `useParams` from `react-router-dom` for path parameters.
4. **Styles.** Only if needed: `frontend/src/pages/<Name>Page.css`, imported in the component.
5. **Verify.** From `frontend/`: `npm run format && npm run lint && npm run build`.

## Constraints

- `any`, `enum`, and constructor parameter properties are forbidden (`erasableSyntaxOnly`).
- Do not add npm dependencies. If one is truly required, stop and ask.
