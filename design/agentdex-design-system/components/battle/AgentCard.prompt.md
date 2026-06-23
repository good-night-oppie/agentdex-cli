Roster card for a single agent — name, type badges, format meta, and a generation/status line. Stack them in the left roster rail; mark the in-focus one `selected`.

```jsx
<AgentCard name="Apex-7" types={['fire','dark']} meta="gen9 OU · 6-mon team"
           gen={3} status="active battle" rating={1487} selected />
<AgentCard name="Sigma-1" types={['psychic','steel']} gen={1} status="pending evo" pending />
```

- `selected` lifts the lime ring; `pending` flips the gen/status line to gold.
- `rating` (ELO) renders top-right in gold; omit for unrated recruits.
- Composes `TypeBadge`.
