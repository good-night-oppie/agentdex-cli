A single Dex-style stat row (label · value · bar) — stack six of them for an agent's genome stat block. Bar color auto-keys off the stat name.

```jsx
<StatBar label="SpA" zh="特攻" value={145} highlight />
<StatBar label="Spe" zh="速度" value={138} />
```

- Recognized labels (`hp/atk/def/spa/spd/spe`) get canonical colors; anything else uses `--accent-primary` or your `color`.
- `highlight` tints the value text to flag the agent's win-condition stat.
- `max` defaults to 200 (gen9 stat ceiling-ish); lower it for tighter scales.
