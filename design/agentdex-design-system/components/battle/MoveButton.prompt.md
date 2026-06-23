A single battle move slot — name, type badge, category, and PP. Lay four in a grid for the move panel.

```jsx
<MoveButton name="Flamethrower" type="fire" category="Special" pp={15} ppMax={15} selected />
<MoveButton name="Shadow Ball" type="ghost" category="Special" pp={0} ppMax={15} />
```

- PP at 0 disables and dims the button; PP ≤25% turns the counter red.
- `selected` adds the lime active ring (`--glow-active`).
- Composes `TypeBadge` for the type chip — pass a known type name.
