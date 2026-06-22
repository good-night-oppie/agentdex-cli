Trichrome battle HP bar — green/amber/red driven by the remaining HP fraction, with an animated drain; use it anywhere an agent's health is shown (battle scene, dex card, roster).

```jsx
<HPBar name="HP · Apex-7" zh="生命值" cur={410} max={450} />
```

- State auto-derives from `cur/max` (`ok` >45%, `warn` ≤45%, `low` ≤20% with a pulse, `fainted` at 0). Override with `state` if a server snapshot disagrees.
- `showValues={false}` for a bare track (e.g. compact roster rows); pass `height` to thicken it for the hero battle scene.
- Respects `prefers-reduced-motion` — the low-HP pulse degrades to a static red.
