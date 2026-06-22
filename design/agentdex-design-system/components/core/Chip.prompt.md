Mono status pill for the topbar — format chips, lane, LIVE, SSE state. `tone="live"` blinks a red dot.

```jsx
<Chip tone="ok">gen9 OU</Chip>
<Chip tone="live">LIVE · sandbox</Chip>
<Chip tone="data">● SSE connected</Chip>
```

- `tone`: `default` · `ok` (lime) · `live` (red, blinking dot) · `gold` · `data` (blue)
- Always IBM Plex Mono. Keep copy terse and lowercase except acronyms (LIVE, SSE, OU).
