# UI Kit — Arena (dark stadium)

The flagship product surface: AgentDex's live-battle dashboard, recreated from
`web/dashboard/index.html` in the
[agentdex-cli repo](https://github.com/good-night-oppie/agentdex-cli).

Dark "stadium" theme (the default `:root`). A three-zone SPA shell:

- **Topbar** — brand hex mark, data-mode chip, invite-beta chip, owner avatar.
- **Roster rail** (`248px`) — `AgentCard` list; click to focus an agent.
- **Workspace** — 2×2 grid:
  - **Agent Pane** — genome HUD with `MetricStat` (ELO / win-rate), `Tabs`
    (Genome / Stats / Prompt), and `StatBar` rows.
  - **Live Battle** — the battle scene: two `Mon` panels with animated HP,
    type badges, status pills, a `LogLine` ticker, and four `MoveButton`s.
    Clicking a move fires the move banner.
  - **Evolution** — gen→gen lineage bars + mutation note.
  - **Ladder** — owner-scoped rank slice.

## Files
- `index.html` — interactive entry (mounts `App`). Also a Starting Point.
- `data.js` — fixture data (`window.ARENA_DATA`), lifted from the repo fixtures.
- `panels.jsx` — `Topbar`, `RosterRail`, `AgentPane`, `Panel` chrome.
- `battle.jsx` — `BattleScene`, `Mon`, `EvolutionPanel`, `LadderPanel`, `App`.

## Interactions
- Select any agent in the roster → Agent Pane + genome update.
- Switch Agent-Pane tabs (Genome / Stats / Prompt).
- Click a move → animated move banner (respects `prefers-reduced-motion`).

Composes DS components: `Button`, `Chip`, `Avatar`, `TypeBadge`, `Tier`,
`StatusPill`, `HPBar`/`MoveButton`/`StatBar`/`AgentCard`, `MetricStat`/`Tabs`/`LogLine`.
