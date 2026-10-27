---
name: tailwind
description: Tailwind CSS v4 conventions for this frontend - design tokens from the Canva deck in @theme, utility-first styling, responsive and accessible patterns, class ordering, when to extract a component. Use when styling or restyling any React component, adding colors/spacing/typography, or when asked "make it look like the design", "style this", "add dark mode", "is this responsive".
---

# Tailwind CSS v4 (frontend)

The frontend is styled **only** with Tailwind utilities. No CSS modules, no styled-components, no inline `style={{}}`
except for truly dynamic values (e.g. a progress width). The only stylesheet is `frontend/src/index.css`.

## Setup facts

- Tailwind v4 via `@tailwindcss/vite` (see `vite.config.ts`). There is no `tailwind.config.js`; configuration is CSS-first.
- `src/index.css` = `@import 'tailwindcss'` + `@theme { ... }` tokens + a tiny `@layer base`.
- `prettier-plugin-tailwindcss` sorts classes on `npm run format`. Never hand-order classes; run the formatter.

## Design tokens (from the Canva deck «шашлички-1»)

| Token | Use |
|---|---|
| `olive-300` | page background |
| `olive-900` / `olive-800` | primary / secondary text, dark buttons |
| `olive-100` / `olive-200` | chips, subtle fills, borders |
| `cream-50` / `cream-100` | cards and inputs, raised cards |
| `accent-500` / `accent-600` | primary action, "to buy" markers, errors |
| `font-display` (Fraunces) | headings and the logo only |
| `font-sans` (Inter) | everything else |
| `rounded-card`, `shadow-card` | the card surface |

Add a token by extending `@theme`; never type a raw hex in a component. If the design needs a new color, add a scale step
(`--color-olive-500`), not a one-off.

## Writing classes

- **Mobile first.** Base classes are the phone layout; `sm:` (640), `md:` (768), `lg:` (1024) add up. The design must work from 320 px.
- **Spacing scale only.** `p-4`, `gap-6`, `mt-10`; arbitrary values like `p-[13px]` need a comment and are a smell.
- **Layout with flex/grid**, not margins on children: `flex gap-3`, `grid gap-6 sm:grid-cols-2`.
- **State variants in this order of preference:** `hover:`, `focus-visible:` / `focus:`, `disabled:`, `aria-pressed:`/`aria-expanded:`/`data-[state=...]:`. Prefer ARIA-driven variants over extra boolean props for visual state.
- **Focus is mandatory.** Every interactive element has a visible focus ring: `focus:ring-2 focus:ring-accent-500 focus:outline-none` (or `focus-visible:`).
- **Color + opacity** with the slash syntax: `bg-accent-500/15`, `text-olive-800/70`.
- **Conditional classes:** template literal with a ternary for one switch; for more than two, compute a `const classes = ...` above the JSX. No `clsx` dependency unless the team agrees.
- **Dark mode:** not in scope. Do not add `dark:` variants.

## Components vs `@apply`

- Repeating the same 8+ classes in three places → extract a React component (`<Button variant="primary">`), not an `@apply` class. Components carry behaviour and a11y; `@apply` only carries styles.
- `@apply` is allowed only inside `@layer base` in `index.css` for `body`/typography defaults.

## Typography

- Headings: `font-display font-bold` with `text-3xl sm:text-4xl` scale; body `text-base`, helper text `text-sm`/`text-xs` with `text-olive-800/70`.
- Line length: wrap prose in `max-w-xl`/`max-w-2xl`.
- Ukrainian text: use real apostrophe `'` in strings is fine; typography of quotes «» in UI copy.

## Accessibility checklist for any styled component

- Semantic element first (`button`, `a`, `fieldset/legend`, `dl`), then classes.
- Contrast: text on `olive-300` background must be `olive-900`/`olive-800` or `cream-50` for headings; never `olive-600` body text on `olive-300`.
- Loading state: `aria-busy` on the form, `role="status"` on the placeholder; errors `role="alert"`.
- Touch targets ≥ 40 px (`min-h-10` / `size-10`).

## Review checklist

1. Raw hex / arbitrary values? → token.
2. Missing `sm:`/`md:` where the desktop design differs? → add.
3. Missing focus styles? → add.
4. Class soup duplicated? → component.
5. Ran `npm run format`? Classes are sorted.
