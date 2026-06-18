---
title: "ADR-0013: First-time-user onboarding — pip-install, `adx login` (GitHub device-flow), enrollment wizard, account↔token bridge"
status: draft
owner: "@EdwardTang"
created: 2026-06-18
updated: 2026-06-18
type: reference
scope: docs/adr
layer: cross-cutting
cross_cutting: true
---

# ADR-0013: First-time-user onboarding

> **Status: proposed (design-first).** This ADR is the agreed design before any
> code, per the owner's `/goal` decision (2026-06-18). It specifies the
> adx-cli ↔ adx-core split so each lane can build in parallel against a fixed
> contract. Login mechanism: **GitHub device-flow** (owner-selected).

## 1. Context — what exists today vs. the target journey

**Target first-time-user journey (owner's vision):**

```
pip install agentdex-cli[bene]            # adx on PATH, no `uv run`
→ sign up on agentdex.builders (human, in the browser)
→ adx login                               # OAuth to that account
→ onboarding wizard                       # enroll your agent(s)
→ your agent plays (MCP or `adx arena play`)
→ adx status                              # check agents / battles in the TUI
```

**What the codebase has today (recon 2026-06-18):**

- **Identity is per-agent consent tokens, not human accounts.** `consent.py`
  models a human "owner" as a bare **email string**; enrollment is
  email → out-of-band confirmation code (`/enroll/request` → file/webhook
  inbox → `/enroll/confirm/{code}`) → an Ed25519, capability-scoped,
  PoP-bound consent token keyed by `(owner, agent_name)`. There is **no human
  account, no session, no OAuth, no `adx login`** anywhere in the tree.
- **`adx` commands:** `bridge / expedition / langfuse / pool / deploy / arena`
  (the TUI is `adx arena play`). No `login`, `onboard`, `account`, or `status`.
- **Distribution:** the `adx` console-script entry point already exists
  (`packages/agentdex_cli/pyproject.toml` → `[project.scripts] adx =
  "agentdex_cli.cli:main"`), but `agentdex-cli`'s dependencies are all **uv
  workspace** members (`agentdex-engine`, `agentdex-plugin`, `agentdex-observe`,
  `adx-bridges`, `helios-client`) resolved via `[tool.uv.sources]`. None are on
  PyPI, so `pip install agentdex-cli` from PyPI fails today — only `uv run adx`
  works. There is **no `[bene]` extra**.
- **Hosting:** `agentdex.builders` is **not yet live** (DNS → registrar
  parking, no TLS — see ADR-0012 follow-ups / `AWS-PUBLIC-DNS-TLS`). The live
  arena is `https://agentdex.ai-builders.space` (Koyeb) + the raw AWS box.

So the goal **adds a human-account + OAuth identity layer** on top of the
existing per-agent consent-token model, plus a real PyPI distribution.

## 2. Decision

### D1 — Distribution: `pip install agentdex-cli[bene]` → `adx`

- Keep the existing `adx = agentdex_cli.cli:main` console-script (already
  correct — after a real install, `adx` lands on PATH with no `uv run`).
- Publish the **runtime** workspace packages the CLI imports
  (`agentdex-engine`, `agentdex-plugin`, `agentdex-observe`, `adx-bridges`,
  `helios-client`, and their first-party deps) to PyPI under the agentdex
  namespace, with pinned floor versions, so `pip install agentdex-cli` resolves
  off-PyPI. The `[tool.uv.sources]` workspace pins stay for local dev; release
  builds resolve the published versions.
- Add a **`[bene]` extra**: `[project.optional-dependencies] bene =
  ["bene>=0.2.1"]` (bene is published at 0.2.1), so `pip install
  agentdex-cli[bene]` pulls the BENE harness — letting an agent drive arena play
  through BENE (planner/executor, eval gates) rather than hand-rolled glue.
- Keep heavy/optional surfaces (camoufox bridge, langfuse stack) behind their
  own extras so the base install stays lean.
- A release pipeline (`adx release` already exists in spirit) tags + builds +
  publishes the workspace members in dependency order.
- **Release gate + creds:** the operator holds the PyPI token (owner, 2026-06-18);
  the publish happens **last** — `pip install agentdex-cli[bene]` ships only once
  the play loop (login → wizard → enroll → play → status, P2–P5) is fully
  working. The packaging *config* (the `[bene]` extra, version floors, the
  publish workflow) is built up front and dry-run-validated against TestPyPI, but
  the production publish to PyPI is the final step, not the first.

### D2 — `adx login`: GitHub device-flow

Device-flow (not a localhost callback) because it is the robust CLI idiom — no
redirect-URI registration, no local web server, works over SSH:

```
adx login
  → POST {ARENA}/auth/device/start            # CLI asks the agentdex backend
  ← { user_code, verification_uri, device_code, interval, expires_in }
  → print: "Open https://github.com/login/device and enter ABCD-1234"
  → poll  POST {ARENA}/auth/device/poll {device_code}   every `interval`s
  ← { status: "pending" } … then { session_token, owner, expires_at }
  → save ~/.agentdex/session.json (0600): { session_token, owner, expires_at, base }
```

agentdex.builders' backend owns the GitHub OAuth app and brokers the flow
(the CLI never sees the GitHub client secret). The returned **session token**
is an agentdex-issued JWT/opaque token that authenticates the human to their
account; `adx logout` deletes the file; `adx whoami` shows the logged-in owner.

### D3 — Account ↔ consent-token bridge (the load-bearing seam)

The human account becomes the canonical **owner**, and that owner is the
account's **verified email** — *not* the GitHub numeric id. This choice is
load-bearing: memberships and battle quota are keyed by
`_normalize_owner(claims.owner)`, and every existing (email-OOB) enrollment
already supplies the owner email, so a GitHub-id owner would split the *same
human's* paid membership and quota continuity across two keys. `/enroll/account`
therefore mints tokens with the verified email as `ConsentClaims.owner` (the
GitHub identity is used only to *prove* that email), which slots in without
changing the quota/membership model. If adx-core ever keys the account store by
a GitHub/account id instead, it must carry an explicit account-id ↔ email
lookup so every store stays single-keyed per human. A logged-in human mints
per-agent consent tokens **without the email-OOB code** — the session *is* the
human proof:

```
adx enroll <agent_name>        (authenticated by the session)
  → POST {ARENA}/enroll/account   Authorization: Bearer <session_token>
                                  body { agent_name, agent_pubkey_hex }
  ← { token }                     # same ConsentClaims shape as today
```

`/enroll/account` reuses `ConsentAuthority.mint` and the existing
`(owner, agent_name)` keying, so **MCP and `adx arena play` keep working
unchanged** — the only new thing is *how the token is obtained*. The legacy
email-OOB path (`/enroll/request` + `/enroll/confirm`) stays for users without
an account (anti-lockout), exactly as today.

**Global agent-name uniqueness is load-bearing — `/enroll/account` must enforce
it identically to the email-OOB path.** The consent *token* is keyed by
`(owner, agent_name)`, but the arena's *public* identity is keyed by
`agent_name` **alone**: `ArenaGateway.enroll_request` rejects any duplicate
sanitized name globally (`409 agent name already registered` against the global
`_registered` set, plus the reserved-name guard) and the ladder indexes entrants
by name (`agentdex_engine/.../modules/arena/ladder.py`). So `/enroll/account`
must run the **same** reserved-name checks, the **same** global `_registered`
rejection, and append the **same** `register` event as the email-OOB path —
account-enroll changes only *how* a name is claimed, never *whether* it is
globally unique. If it allowed the same name under two different accounts, two
owners' tokens would collapse onto one public ladder/badge identity (a D7
anti-impersonation break). adx-core implementing this contract must therefore
share the one enrollment validator, not fork a per-account one.

### D4 — Onboarding wizard (`adx onboard`)

First-run guided flow (idempotent, resumable):

1. No session → run `adx login` (D2).
2. Pick an agent name (default `terminal-player-<hash>` per the CLI's existing
   default-name logic) → generate + save an Ed25519 keypair at
   `~/.agentdex/<agent>.key`.
3. Enroll under the account (D3) → save the consent token.
4. Choose how the agent plays: **(a)** `adx arena play` (you drive a battle in
   the TUI), or **(b)** MCP (`{ARENA}/mcp/`) so an external agent acts, or
   **(c)** a BENE-driven agent (requires the `[bene]` extra).
5. Play a first **sandbox** battle to confirm the loop end-to-end.

`adx onboard` is also what a bare `adx arena play` falls into when it detects no
session + no token (replacing today's ad-hoc enroll prompt).

### D5 — Agents play (unchanged surfaces)

The minted consent token works with the existing `/mcp/` surface and
`adx arena play`. The `[bene]` extra adds a thin adapter so a BENE
planner/executor agent uses the MCP tools (`request_evolution`, battle
state/choose) under the account's token. No arena-protocol change.

### D6 — `adx status` (TUI)

Authenticated by the session, a one-screen dashboard: the account's enrolled
agents + their key/token health, per-UTC-day quota remaining (battle/evolve/
badge_mint), live/recent battles, and ladder standing. Reads existing surfaces
(`/whoami`, `/my/events`, `/ladder`, `/metrics`) — no new battle backend needed,
only the account→agents join (D7).

### D7 — adx-cli ↔ adx-core wire contract (who builds what)

| Lane | Builds |
|---|---|
| **adx-cli** (this repo) | `adx login` device-flow client + session store · `adx logout` / `adx whoami` · `adx onboard` wizard · `adx enroll` (account-authed) · `adx status` TUI · the `[bene]` adapter · packaging (D1) |
| **adx-core / infra** | agentdex.builders web signup (GitHub federation) · the account backend (github_id ↔ owner) · `POST /auth/device/start` + `/auth/device/poll` (the GitHub OAuth app lives here) · `POST /enroll/account` (session-authed mint) · the account→agents join for `/status` · `agentdex.builders` DNS/TLS (`AWS-PUBLIC-DNS-TLS`) |

**Frozen contract surface (so both lanes build in parallel):** the
`/auth/device/start|poll` request/response shapes (D2), the session-token
bearer scheme, and `/enroll/account` (D3). adx-cli builds against these shapes;
adx-core implements them.

## 3. Phasing — tiny-PR roadmap (adx-cli lane)

Build the **play loop first; release last** (per the owner: ship to PyPI once
agentdex-cli is fully ready for play; the PyPI token is in hand):

- **P1 — `adx login`.** Device-flow client + `~/.agentdex/session.json` +
  `logout`/`whoami` (against the frozen D2 contract; a stub/mock backend for
  tests).
- **P2 — `adx onboard` + `adx enroll`.** The wizard + account-authed enroll (D3/D4).
- **P3 — `adx status`.** The TUI dashboard (D6).
- **P4 — `[bene]` adapter.** BENE planner/executor drives the MCP play loop (D5).
- **P5 — Packaging config.** Add the `[bene]` extra + version floors + the
  publish workflow; dry-run against TestPyPI.
- **P6 — Release.** Once P1–P5 + the adx-core backend are live and the journey
  works end-to-end, publish to PyPI (operator runs it with the held token).

Each adx-cli phase ships as tiny PRs against the frozen contract; adx-core
builds the backend (D7) in parallel.

## 4. Alternatives considered

- **Browser OAuth callback** (localhost redirect server) instead of device-flow
  — matches the owner's original phrasing but is more fragile for a CLI (port
  conflicts, no-browser/SSH hosts, redirect-URI registration). Device-flow is
  the dev-tool norm (gh, aws, gcloud). Rejected for the default; can be added
  later for browser-first desktops.
- **No OAuth — magic-link wizard over the existing email-OOB enroll.** Least new
  infra, but it is not the account-based login the goal asks for. Kept only as
  the anti-lockout fallback (D3).
- **Single self-contained wheel** instead of publishing each workspace member —
  simpler `pip` story but loses independent versioning + duplicates code that
  `agentdex-arena`/server also ship. Rejected; publish the namespace.

## 5. Open items for adx-core / infra (not adx-cli's lane)

- `agentdex.builders` must be live (DNS A-record → arena box + Caddy auto-TLS)
  before the hosted signup + device-flow are real (`AWS-PUBLIC-DNS-TLS`,
  blocked). Until then the CLI's `--url` / `ADX_ARENA_URL` points at the live
  `agentdex.ai-builders.space`.
- A GitHub OAuth app (client id/secret) registered to the backend — a
  credentials decision owned by the operator; the secret never reaches the CLI.
- The account datastore (github_id ↔ owner) + the account→agents join for
  `/status`.

## 6. Consequences

- The per-agent consent-token model, quota keying, and arena protocol are
  **unchanged** — `/enroll/account` is purely a new way to *obtain* today's
  token, so MCP + `adx arena play` are untouched.
- Logged-in users skip the email-OOB step (smoother onboarding); the OOB path
  survives as the no-account fallback.
- A real PyPI distribution unblocks `pip install agentdex-cli[bene]` → `adx`,
  removing the `uv run` requirement for end users.
