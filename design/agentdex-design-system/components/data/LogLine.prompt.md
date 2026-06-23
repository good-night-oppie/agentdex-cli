A single mono log line with a timestamp and tone-colored body — the unit of both the battle ticker and the reasoning trace. Stack many in a scrollable feed.

```jsx
<LogLine ts="T06" tone="eff">Super effective! <b>247 dmg</b></LogLine>
<LogLine ts="T07" tone="decide" label="DECIDE">Dark Pulse for the KO</LogLine>
<LogLine ts="T07" tone="faint">Vertex-3 fainted!</LogLine>
```

- `tone` maps to semantic colors (agent=blue, decide/heal=lime, dmg=rust, eff=gold, faint=red).
- `label` prints a bold tag before the body (great for trace DECIDE/THINK lines).
- Body accepts rich inline nodes — bold move names, nested colored spans.
