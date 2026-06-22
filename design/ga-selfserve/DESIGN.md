# GA-DESIGN — AgentDex Arena self-serve flow

**Card:** GA-DESIGN (lane `ga-selfserve`, P0) · **Lead:** adx-cli ·
**Reviewers (sign-off required before build):** adx-core, bene, bene-core ·
**Spec:** `/home/admin/gh/harness-engineering/tasks/agentdex-arena-ga/SPEC.md`
**Blast radius:** `agentdex-cli:design/**` (this deliverable lives entirely under `design/ga-selfserve/`).

This is the design that **gates every build card** (GA-AUTH, GA-ENROLL, GA-ARENA-MODES,
GA-SELFPLAY-EVOLVE, GA-PAID-STRIPE, GA-DEPLOY). Build starts only after reviewer sign-off.

---

## What this is

A **clickable prototype of the full invited-user funnel**, built on the
`agentdex-design` system (the same `styles.css` + `_ds_bundle.js` the Arena/Ladder kits use —
real components, real tokens, not mockup CSS).

- **One URL:** `design/ga-selfserve/index.html`. Click the **prototype ›** jumper (top bar) or
  use a deep link (`index.html#enroll`) to land on any screen.
- **Light "Patagonia paper"** for the onboarding funnel; **dark "stadium"** when you reach the
  arena mode-select (theme flips on `<html data-theme>`), so the user *feels* entering the arena.

### How to view
```
cd design && python3 -m http.server 8099
# → http://localhost:8099/ga-selfserve/index.html   (deep links: #signup #login #github #enroll #modes #billing)
```
Render-verified headless (chromium `--dump-dom`): all 6 screens boot (`data-spa="ready"`), no throw.

---

## Flow → screen map (covers SPEC §2 end to end)

| Step | Screen (`#hash`) | Theme | Covers |
|---|---|---|---|
| 01 Account | `#signup` / `#login` | light | Invite code → email + password signup; login + magic-link alt |
| 02 Connect GitHub | `#github` | light | GitHub OAuth, **read-only** scopes shown (`read:user`, `public_repo` read, **no write**) |
| 03 Enroll agent | `#enroll` | light | Pick **openai/codex · opencode · claw-code** (`ultraworkers/claw-code`); type-badged choice cards; mints Ed25519 identity |
| 04 Arena mode | `#modes` | **dark** | Single-vs-Bots (free) · 1v1 owner (free) · **[PAID]** Team battle · **[PAID]** Self-play-evolve (**poke-env**) |
| 05 Go live | `#launch` (free/unlocked) · `#billing` (paid-locked) | **dark** (launch) / light (billing) | **`#launch`** = terminal arena confirmation: enrolled agent + mode + queue/Start-battle. **`#billing`** = the conditional sub-step only paid-locked users hit: **Stripe** ($19/mo) **and** invite path (**$0 / 3-mo full set**), biller **Good Night Oppie LLC**; on redeem/pay → `#launch`. |

Free / already-unlocked modes go straight to **`#launch`** (never through Stripe). Paid-locked modes
route to `#billing` first. The persistent **stepper** (01→05) tracks the journey; step 05 "Go live"
maps to the launch surface, with billing as a conditional detour — not the journey's end.

---

## Design decisions (the why)

1. **Funnel = light paper, arena = dark stadium.** Matches the system's two-surface doctrine
   (Ladder light / Arena dark). The theme flip at mode-select is the "lights up, you're in the
   arena" moment — motion + color do the narrative work.
2. **Real components, not bespoke CSS.** Every control is `DS.Button/Card/Chip/TypeBadge/…`
   with valid props per the `.d.ts`. This keeps the design 1:1 buildable — engineers wire data,
   not re-implement UI. Where the system lacked a funnel control (labeled `Field`, `Stepper`,
   `AuthShell`), those live in `shell.jsx` as thin token-only additions (candidates to promote
   into the system later).
3. **Anti-pay-to-rank is loud, by construction.** Mode-select and billing both state paid adds
   *formats, never rating*; the trust footer repeats it bilingually on every screen.
4. **Invite-first.** The 100-seat invite ($0 / 3 months full paid) is the hero of signup and the
   primary billing path; Stripe card entry is the secondary "or subscribe".
5. **Bilingual EN/ZH gloss** throughout (EN canonical, 中文 trails via `--font-zh`); **glyph-first,
   no emoji**; reduced-motion honored.

---

## Files
```
design/ga-selfserve/
  index.html    mount (React UMD + Babel + ../agentdex-design-system/{styles.css,_ds_bundle.js})
  data.js       fixtures — agents, modes, plan, invite, stepper steps
  shell.jsx     shared chrome — Hex, Eyebrow, Gloss, Field, Stepper, FunnelNav, AuthShell, WhyRail, TrustFooter
  screens.jsx   6 screens + FunnelApp router (hash deep-links + theme switch)
  DESIGN.md     this file
```

---

## For reviewers — please sign off on

- **adx-core** (builds AUTH/ENROLL/PAID): is the signup→login→GitHub→enroll→billing surface +
  the OAuth scope contract + Stripe/invite flow what you'll build against?
- **bene-core** (ARENA-MODES): do the four mode cards + the free/paid gating match the
  mode-selection ↔ backend contract you need?
- **bene** (SELFPLAY-EVOLVE): is the self-play-&-evolve mode framed correctly (poke-env substrate,
  success/speed/cost eval, evolution seeds)?

Per policy: **a review comment is resolved only by its author.** No build PR merges until
GA-DESIGN is signed off here.

## Open questions for reviewers
- **bene (GA-SELFPLAY-EVOLVE):** the self-play mode card is a placeholder for your substrate — once you
  publish the run/eval/generation data shapes (#724), I'll bind the card's fields (success/speed/cost,
  generation, kill-gate verdict) to them. Confirm the framing (poke-env, eval-ranked, evolution seeds) is right.
- **adx-core (GA-AUTH/PAID):** (a) is GitHub a *connect* step only, or also a primary login? (prototype:
  email+password+magic-link login, GitHub connect after). (b) Confirm the invite-redemption contract
  (100 → $0/3-mo) and that the billing trigger is **paid-mode-only** (free modes skip Stripe → `#launch`).
- **All:** the prototype models UI state only — no real auth/Stripe/queue calls. Copy avoids over-claiming.

## CHANGELOG
- **v1** — 7-screen clickable prototype on the design system (signup·login·github·enroll·modes·billing·launch).
- **Reviews:** bene-core external **sign-off ✅** (data.js/shell.jsx/screens.jsx, 100% §2 coverage); internal
  3-lens adversarial pass. _DS-adherence + voice/a11y subagent lenses hit API-529 ×2 → covered instead by
  bene-core's detailed adherence PASS + a manual token/emoji/font scan (0 stray hex) + a manual a11y pass._
- **Fixes applied from review:**
  - Added terminal dark-stadium **`#launch`** screen — free/unlocked modes no longer dead-end in the Stripe
    screen (SPEC §2 "start Arena" surface). Billing is now a conditional sub-step for paid-locked users only.
  - Decoupled stepper **step 05 "Go live"** from the billing screen (id `golive`), so a free user's journey
    doesn't end on a payment screen.
  - **a11y:** `AgentChoice`/`ModeCard`/inline auth links are now keyboard-operable (`role=button`, `tabIndex`,
    Enter/Space, `aria-pressed`/`aria-label`) + a global `:focus-visible` ring; `prefers-reduced-motion` honored.
  - Aligned `mode.id` to bene-core's GA-ARENA-MODES build contract (`solo_bots|pvp|team|selfplay`).
  - Tightened team-mode title to "Your Two Agents — Team Battle" (SPEC "user Agents team up").
  - bene-core notes (1) `DS.Button.iconLeft` and (2) `DS.Card.selected`/`state` — both confirmed present in the
    `.d.ts` contracts; usage is valid. (3) free-mode billing skip — done via `#launch`.
- **adx-core sign-off ✅ (build-truth alignments applied, their explicit recommendations):**
  - **Passwordless** (ADR-0013, backend has no password primitive) — dropped the Password fields on
    signup + login; the auth primitives are now **email magic-link** + **one-click GitHub login** (matches
    `device_flow.py` / `/auth/email/start`). The prototype no longer shows an unbuildable password path.
  - **Stripe = V2 / coming-soon** (zero code in repo, blocked on the op Stripe item, SPEC §7) — the Stripe
    card is now disabled + "coming soon · V2"; the **live V1 paid path is invite-redeem → membership**
    (`/enroll/redeem-invite` → `/admin/grant-membership`), which adx-core confirmed is fully built.
  - adx-core's remaining nits (off-scale fontSize 13.5/10.5/11.5 vs `--fs-*`; raw `#1a2030` radial) are
    tracked by adx-core for the production build / DS-promotion of `Field`/`Stepper`/`AuthShell`.

## Two gates (don't conflate)
1. **Design-review sign-off** (SPEC §0/§3, via A2A): adx-core ✅ + bene-core ✅ (2/3) · bene pending. Unblocks build cards.
2. **Probe-gate mark-done** (`scripts/kanban_probe_gate.py`): requires a **harness-authored probe → ACCEPT** +
   **db-backed approvals from `eddie-agi-kb` + `harness`** (the two `APPROVERS`), all behind `KANBAN_GATE_ACTOR`.
   The card owner (adx-cli) **cannot** author the probe or grant these — by design (uid-split actor boundary).
   GA-DESIGN reaching board-`done` is harness's ceremony to run once the deliverable + design sign-offs are in.

## Upstream blockers (SPEC §7 — for Eddie, do not block the design wave)
- **Lightsail `agentdex-arena-1` access** — blocks GA-DEPLOY only.
- **op Stripe item (Good Night Oppie LLC)** — 1Password item id for the Stripe key (referenced
  via `op` at point of use, never printed) — blocks GA-PAID-STRIPE only.
