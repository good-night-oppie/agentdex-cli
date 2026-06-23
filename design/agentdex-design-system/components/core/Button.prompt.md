Action button — lime-fill primary for the single true CTA, ghost/secondary/danger otherwise. Geometric Chakra Petch, rounded, snappy press.

```jsx
<Button variant="primary" size="md">+ Enroll agent</Button>
<Button variant="ghost">Queue battle</Button>
<Button variant="danger" size="sm">Forfeit</Button>
```

- `variant`: `primary` (lime, dark text) · `secondary` (raised gray) · `ghost` (lime outline) · `danger` (red wash)
- `size`: `sm` 28px · `md` 36px · `lg` 44px
- `iconLeft` / `iconRight` accept any node. Use one primary per view — the arena is data-dense, so keep CTAs scarce.
