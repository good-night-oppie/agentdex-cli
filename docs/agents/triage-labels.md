---
title: "Agent skills — triage label vocabulary"
status: active
owner: "@EdwardTang"
created: 2026-07-14
updated: 2026-07-14
type: reference
scope: docs/agents
layer: cross-cutting
cross_cutting: true
---

# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the actual label strings used in this repo's issue tracker.

| Label in mattpocock/skills | Label in our tracker | Meaning                                  |
| -------------------------- | -------------------- | ---------------------------------------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate this issue  |
| `needs-info`               | `needs-info`         | Waiting on reporter for more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for an AFK agent  |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation            |
| `wontfix`                  | `wontfix`            | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding label string from this table.

Edit the right-hand column to match whatever vocabulary you actually use.

## Repo state (as of setup, 2026-07-14)

`wontfix` **already exists** in `good-night-oppie/agentdex-cli` (it's a GitHub
default label) — `/triage` will reuse it, not duplicate it. The other four
(`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`) do **not**
exist yet and will be created on first use:

```sh
gh label create needs-triage    --repo good-night-oppie/agentdex-cli --color FBCA04 --description "Maintainer needs to evaluate this issue"
gh label create needs-info      --repo good-night-oppie/agentdex-cli --color D4C5F9 --description "Waiting on reporter for more information"
gh label create ready-for-agent --repo good-night-oppie/agentdex-cli --color 0E8A16 --description "Fully specified, ready for an AFK agent"
gh label create ready-for-human --repo good-night-oppie/agentdex-cli --color 1D76DB --description "Requires human implementation"
```

These five are orthogonal to the repo's existing labels (`bug`, `enhancement`,
`documentation`, `dependencies`, `python:uv`, …) — a triage role and a type label
coexist on the same issue. No renaming was needed.
