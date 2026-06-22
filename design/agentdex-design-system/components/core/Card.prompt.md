The arena's core container — every panel is a Card with an uppercase-mono header strip and a scrollable body.

```jsx
<Card title="Live Battle" headerRight="gen9 OU · turn 7">
  …battle scene…
</Card>
<Card title="Genome" state="winner">…</Card>
<Card padded={false}>…full-bleed sprite zone…</Card>
```

- `title` renders the mono header; omit for a bare card.
- `headerRight` is the meta slot (format, turn, SSE status).
- `state`: `selected` → lime ring · `winner` → gold ring.
- `padded={false}` for battle scenes / imagery that should bleed to the edge.
