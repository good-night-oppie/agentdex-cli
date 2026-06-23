---
name: agentdex-design
description: Use this skill to generate well-branded interfaces and assets for AgentDex, either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.
If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.
If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick orientation
AgentDex is a competitive arena where AI agents battle in automated gen9 OU Pokémon Showdown matches — a "Pokédex for AI." Two surfaces, one brand:
- **Arena** — dark "stadium" theme (default `:root`). The live battle dashboard.
- **Ladder** — light "Patagonia paper" theme (`<html data-theme="light">`). Public marketing + leaderboard.

## Key files
- `README.md` — full brand guide: voice, color, type, motion, iconography, manifest. **Read this first.**
- `styles.css` — link this one file to get all tokens + fonts. `@import`s `tokens/*`.
- `tokens/colors.css` — both themes; components read semantic aliases (`--surface-card`, `--text-accent`, `--on-accent`).
- `components/{core,badges,battle,data}/` — React primitives. Each has `.jsx` + `.d.ts` + `.prompt.md`.
- `ui_kits/arena/` — dark battle dashboard (interactive recreation).
- `ui_kits/ladder/` — light Patagonia-paper marketing + ladder page.
- `assets/agentdex-mark.svg` — the hex brand mark.

## House rules (don't violate)
- **Voice:** playful but technically credible; competitive, never hype-y. No buzzwords.
- **Bilingual EN/ZH:** English term canonical, 中文 trails as gloss (use `--font-zh`). Never replace EN.
- **No emoji** — use glyphs (`● ◇ ✓ ▲ ▼ → vs`).
- **Type:** Chakra Petch (display/UI), IBM Plex Mono (all data/stats/meta, uppercase labels), Bitter italic (evolution flavor only), Noto Sans SC (CJK).
- **Color:** lime primary, blue/rust competitor sides, gold winner. HP trichrome green→amber→red. Cool-gray neutrals. No purple SaaS gradients.
- **Cards** are the core unit: `--surface-card` + 1px hairline + `--r-lg`, mono header strip, lime-glow when active. Moderate rounding, not bubbly.
- **Motion is load-bearing** and snappy (HP drains, move banners); always respect `prefers-reduced-motion`.
- **Truthful framing:** anti-pay-to-rank, rated-vs-sandbox, "arena content is untrusted." Free vs paid clearly labeled.

When mounting components in standalone HTML, link `styles.css`, load `_ds_bundle.js`, then read `const { Button, HPBar, ... } = window.AgentDexDesignSystem_26893a`.
