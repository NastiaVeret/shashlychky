# 5. Rendering performance (Medium)

## render-keys: keys come from data, are stable, and are unique among siblings

`key={order.id}`, never `key={index}` for lists that reorder, insert or delete; never `key={Math.random()}`.

## render-explicit-conditionals: ternaries, not `&&`, when the left side can be `0` or `NaN`

```tsx
{count && <Badge n={count} />}          // renders "0"
{count > 0 ? <Badge n={count} /> : null}
```

## render-long-lists: virtualise or `content-visibility`

Above a few hundred rows: virtualise (a small library, with team approval) or at least `content-visibility: auto; contain-intrinsic-size: 0 48px;` on each row so the browser skips off-screen layout and paint.

## render-hoist-static-jsx: static elements outside the component

```tsx
const ICON = <svg ...>...</svg>;
function Button() { return <button>{ICON}</button>; }
```

React skips reconciling an element whose reference did not change.

## render-animate-wrappers: animate a wrapping div, not the SVG itself

Transforms on a `<div>` are GPU-composited; transforms on SVG elements often are not. Same for `will-change` on the wrapper only during the animation.

## render-svg-precision: trim SVG decimals

Exported SVGs carry 6-decimal coordinates; 1 to 2 decimals are indistinguishable and halve the size. Run SVGO on assets.

## render-use-transition-pending: `useTransition`'s `isPending` instead of manual loading flags

For state updates that trigger slow renders (switching tabs with heavy content), `startTransition` gives you a correct pending flag with no extra state and no flash of empty content.

## render-activity-for-show-hide: keep state when toggling expensive subtrees

With React 19.2+, `<Activity mode={visible ? 'visible' : 'hidden'}>` preserves DOM and state of a hidden tab; cheaper than remounting on each toggle. For older React: keep the component mounted and toggle `hidden`.

## render-resource-hints: tell the browser what is coming

`<link rel="preconnect">` to the API origin in `index.html` (ours is same-origin, so nothing to do), `preload` for the hero font, `prefetch` for the next route's chunk on intent.

## render-no-layout-thrash-in-effects: read layout, then write, never interleave

In `useLayoutEffect`, batch all `getBoundingClientRect` reads before any style writes.
