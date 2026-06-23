Pokémon-convention type badge — agents and moves are type-coded. Text auto-flips dark on light types.

```jsx
<TypeBadge type="fire" />
<TypeBadge type="dark" />
<TypeBadge label="Electric Terrain" color="rgba(240,184,48,.18)" />
```

- `type`: any of the 18 canonical types → canonical color.
- `color` + `label` for non-type tags (terrain, ability, item).
- `size`: `sm` (in move rows) · `md` (agent header).
