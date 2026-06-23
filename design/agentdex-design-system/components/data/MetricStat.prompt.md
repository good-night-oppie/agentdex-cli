Compact metric tile — a labelled big mono number, optional sub-context and a ▲/▼ delta. Grid them 2-up for the genome HUD or ladder.

```jsx
<MetricStat label="ELO" zh="积分" value="1487" sub="±41 RD" tone="elo" delta={32} />
<MetricStat label="Win rate" zh="胜率" value="76%" sub="38–12" tone="win" />
```

- `tone` colors the number: `elo` gold, `win` lime, `data` blue, `default` ink.
- Numeric `delta` auto-renders ▲ (accent) / ▼ (danger); pass a string to format it yourself.
