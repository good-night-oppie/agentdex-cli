---
title: "weco start claude — primary-source snapshot (docs.weco.ai)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal
layer: cross-cutting
cross_cutting: true
---

actual_route: coordinator_inline_exception

# Primary-source snapshot: docs.weco.ai/using-weco/claude-in-dashboard

Captured 2026-07-11 via WebFetch (user-supplied URL). This page post-dates the
2026-07-10 weco_docs seed (which contains no `using-weco/` section and no
`start` verb) — it supersedes the weco research brief's "Weco CANNOT spawn
agents" finding for this specific feature. M2 spike 1 must empirically verify
the verb (`weco start claude --help`) alongside credit economics.

## Snapshot (paraphrase-faithful reproduction)

**Overview** — "The `weco start claude` command connects a local Claude Code
session to the Weco dashboard, enabling you to run your agent in the terminal
while monitoring it in real-time on the web interface."

**Getting started** — from the project directory: `weco start claude`. "This
starts Claude Code with Weco integration and outputs a dashboard URL for you
to access the mirrored session."

**Drive from either side** — interact through the terminal or the dashboard
chat panel; message the agent in the dashboard to steer the run.

**Stay in the loop** — "Long-running evals don't freeze the conversation. The
bridge tracks the run's progress and feeds status changes back to the agent."

**Flags**

| Flag | Purpose |
|---|---|
| `--headless` | run without local terminal UI; stream to dashboard only |
| `-p, --prompt` | initialize the first turn with a specific prompt |
| `--allow-tools` | auto-approve agent tool calls without per-action prompts |
| `--billing weco` | route LLM calls through Weco's proxy; bill the Weco credit wallet |

**Requirements** — "The Claude Code CLI must be installed locally to use
`weco start claude`." Default auth = local Claude auth (BYO); execution is
local ("Your agent runs natively in your terminal and its conversation
streams live into the dashboard" — earlier fetch of the same page, this
session).

## Design significance

- Verifies the D2 driver mechanism (`adx evolve` wraps `weco start claude`);
  `--headless` + `-p` + `--allow-tools` are exactly the automation surface the
  driver needs.
- Disclosure basis: the session conversation streams to the Weco dashboard.
