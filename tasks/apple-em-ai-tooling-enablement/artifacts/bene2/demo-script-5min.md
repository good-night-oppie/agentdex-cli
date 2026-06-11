---
title: "BENE 0.2.0 verified 5-min demo script"
status: active
owner: "@EdwardTang"
created: 2026-06-11
updated: 2026-06-11
type: reference
scope: "task-prep/apple-em/bene2-kit"
layer: cross-cutting
cross_cutting: true
name: bene2-demo-script-5min
description: Timed 5-minute live demo script on BENE 0.2.0 with real executed command outputs plus the shipped-kernel `bene demo --no-ui` close (supersedes the old spoken 2.0 vision close).
---

# BENE 0.2.0 — 5-Minute Live Demo Script

**Context:** HM screen, Engineering Manager — AI Developer Tools, Apple DevEx (req 200658219-3337). Fri 2026-06-12 11:30 AM PT.
**Demo machine:** run from `/home/admin/gh/bene-main` (repo venv `.venv`, all commands via `uv run`).
**Every command and output below was executed for real on 2026-06-11 against BENE 0.2.0.** ULIDs/timestamps will differ on replay — copy them from your own output. Outputs were captured through a pipe, so BENE auto-emitted JSON; on a live TTY several commands (`ls`, `checkpoint`) render Rich tables instead — same data either way.
**Re-verified end-to-end at HEAD 2026-06-11 evening (post history-rewrite):** every command works; output blocks below refreshed to current shapes (search results now return full rows, `logs` wraps events in an object, `query` includes the `file_read` event).

**Pre-demo setup (run before the call, off-camera):**

```bash
cd /home/admin/gh/bene-main
export BENE_DB=/tmp/bene-demo-$$/bene.db   # throwaway db; BENE_DB env is honored (bene/cli/main.py:27)
mkdir -p "${BENE_DB%/*}"
```

Total live time: **4:00 of commands + 1:00 spoken close = 5:00.**

---

## Beat 0 — What is BENE (0:00 → 0:15)

```bash
uv run bene --version
```

```
bene, version 0.2.0
```

**Say:** "BENE is a local-first multi-agent orchestration framework I built — every agent gets an isolated, auditable virtual filesystem inside one SQLite file. 699 passing tests, 37 MCP tools, CLI + web UI + TUI. Let me show you the loop in five minutes."

**Cumulative: 0:15**

---

## Beat 1 — Init + spawn + ls (0:15 → 1:00)

```bash
uv run bene init
```

```
Initialized BENE database: /tmp/bene-demo-2411717/bene.db
```

The CLI is a thin layer over the `Bene` Python API — spawn an agent and write into its VFS in three lines (no LLM call needed, so it's demo-safe):

```bash
uv run python -c "
from bene import Bene
b = Bene('$BENE_DB')
aid = b.spawn('scout')
b.write(aid, '/notes/plan.md', b'Step 1: face the fear.\n')
print(aid)"
```

```
01KTV320D0KVPG9T3K2083V9TE
```

```bash
uv run bene ls
```

```
[
  {
    "agent_id": "01KTV320D0KVPG9T3K2083V9TE",
    "name": "scout",
    "status": "initialized",
    "created_at": "2026-06-11T10:18:45.536"
  }
]
```

**Say:** "One file on disk is the whole nexus — agents, their files, every event. `--json` everywhere makes it composable with jq and other agents."

**Cumulative: 1:00**

---

## Beat 2 — The Litany loop: checkpoint → mutate → diff → restore (1:00 → 2:00)

*(`AID` = the agent ULID from Beat 1.)*

```bash
uv run bene checkpoint $AID --label before-refactor
```

```
{
  "checkpoint_id": "01KTV32HYZYV5AC6FPKKN19V74",
  "label": "before-refactor"
}
```

Mutate the agent's world (simulating a turn that went wrong):

```bash
uv run python -c "
from bene import Bene
b = Bene('$BENE_DB')
b.write('$AID', '/notes/plan.md', b'Step 1: face the fear.\nStep 2: let it pass through.\n')
b.write('$AID', '/src/refactor.py', b'def helper():\n    return 42\n')"
uv run bene checkpoint $AID --label after-refactor
```

```
{
  "checkpoint_id": "01KTV32J9AHJX2GKVKTW8Y7EKT",
  "label": "after-refactor"
}
```

```bash
uv run bene diff $AID --from 01KTV32HYZYV5AC6FPKKN19V74 --to 01KTV32J9AHJX2GKVKTW8Y7EKT
```

```
          File Changes
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┓
┃ Status     ┃ Path             ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━┩
│ ADDED      │ /src             │
│ ADDED      │ /src/refactor.py │
│ MODIFIED   │ /notes/plan.md   │
└────────────┴──────────────────┘

No state changes

No tool calls between checkpoints
```

```bash
uv run bene restore $AID --checkpoint 01KTV32HYZYV5AC6FPKKN19V74
uv run bene read $AID /notes/plan.md
```

```
Agent 01KTV320D0KVPG9T3K2083V9TE restored to checkpoint 01KTV32HYZYV5AC6FPKKN19V74
{"agent_id": "01KTV320D0KVPG9T3K2083V9TE", "path": "/notes/plan.md", "content": "Step 1: face the fear.\n"}
```

(`bene read $AID /src/refactor.py` now returns `{"error": "File not found: ...:/src/refactor.py"}` — the bad turn is fully unwound.)

**Say:** "That's the Litany Against Fear as an engineering primitive: face the failed turn, see exactly its path with `diff`, restore, and only the clean state remains. Agents get fearless because rollback is cheap and auditable."

**Cumulative: 2:00**

---

## Beat 3 — Knowledge that outlives the agent: memory + skills (2:00 → 2:45)

```bash
uv run bene memory write $AID "Flaky test root cause: NTP drift on runner pool B skews TLS cert validation" -t insight -k ntp-drift
uv run bene memory search "flaky tls"
```

```
[
  {
    "memory_id": 1,
    "agent_id": "01KTW51T8D1AD8H8RZZDG0WQCK",
    "type": "insight",
    "key": "ntp-drift",
    "content": "Flaky test root cause: NTP drift on runner pool B skews TLS cert validation",
    "metadata": {},
    "created_at": "2026-06-11T20:13:06.177"
  }
]
```

(The `memory write` itself also echoes a confirmation JSON — `{"memory_id": 1, …}`.)

```bash
uv run bene skills save -n triage_flaky_test \
  -d "Triage a flaky CI test by separating infra noise from product bugs" \
  -t "Given failing test {test_name}, check runner clock skew, then rerun {retries} times to classify flake vs bug." \
  --tags triage,ci -a $AID
uv run bene skills search "flaky triage"
```

```
[
  {
    "skill_id": 1,
    "name": "triage_flaky_test",
    "description": "Triage a flaky CI test by separating infra noise from product bugs",
    "template": "Given failing test {test_name}, check runner clock skew, then rerun {retries} times to classify flake vs bug.",
    "tags": ["triage", "ci"],
    "source_agent_id": "01KTW51T8D1AD8H8RZZDG0WQCK",
    "use_count": 0,
    "success_count": 0,
    "success_rate": null,
    "created_at": "2026-06-11T20:13:06.728",
    "updated_at": "2026-06-11T20:13:06.728"
  }
]
```

**Say:** "Both stores are FTS5 full-text indexes in the same SQLite file — note the search hit on 'flaky tls' via porter stemming. Skills track use_count and success_count, so reusable patterns earn a track record. The next agent never starts cold."

**Cumulative: 2:45**

---

## Beat 4 — The Breeding Program: meta-harness surface (2:45 → 3:30)

*(Show the command family only — a real search runs for hours.)*

```bash
uv run bene mh --help
```

```
Usage: bene mh [OPTIONS] COMMAND [ARGS]...

  Meta-Harness — automated harness optimization.

Commands:
  frontier   Show the Pareto frontier of a meta-harness search.
  inspect    Inspect a specific harness — source, scores, and trace summary.
  knowledge  Show the persistent knowledge base — discoveries from all...
  lint       Health-check a search archive for issues.
  resume     Resume an interrupted meta-harness search from its last...
  search     Run a meta-harness search to optimize a harness for a...
  status     Show the status of a meta-harness search.
```

**Say:** "This is the evolutionary layer: `search` breeds harness strategies against a benchmark, `frontier` shows the Pareto frontier of quality-vs-cost survivors, `knowledge` accumulates discoveries across runs, and `lint`/`resume` make long searches operable. Harness design becomes a search problem instead of folklore."

**Cumulative: 3:30**

---

## Beat 5 — Observability: every claim checkable (3:30 → 4:00)

One-liner mention: `uv run bene ui` launches the web dashboard (agent graph, events, tool calls); `bene dashboard` is the TUI twin. Then show the raw audit trail:

```bash
uv run bene logs $AID --tail 3
```

```
{
  "agent_id": "01KTW51T8D1AD8H8RZZDG0WQCK",
  "conversation_turns": 0,
  "events": [
    {
      "timestamp": "2026-06-11T20:12:51.673",
      "event_type": "checkpoint_create",
      "payload": "{\"checkpoint_id\": \"01KTW51V2S29FZXTG0CHY3CVJ8\", \"label\": \"after-refactor\"}"
    },
    {
      "timestamp": "2026-06-11T20:12:52.131",
      "event_type": "checkpoint_restore",
      "payload": "{\"checkpoint_id\": \"01KTW51TQDPTHPW35FCXMS8PWE\"}"
    },
    {
      "timestamp": "2026-06-11T20:12:52.370",
      "event_type": "file_read",
      "payload": "{\"path\": \"/notes/plan.md\"}"
    }
  ]
}
```

```bash
uv run bene query "SELECT event_type, COUNT(*) AS n FROM events GROUP BY event_type ORDER BY n DESC"
```

```
[
  {"event_type": "file_write", "n": 3},
  {"event_type": "checkpoint_create", "n": 2},
  {"event_type": "agent_spawn", "n": 1},
  {"event_type": "checkpoint_restore", "n": 1},
  {"event_type": "file_read", "n": 1}
]
```

(Live output pretty-prints one field per line; the `file_read` row appears because Beat 2's `bene read` is itself journaled — a nice aside if asked.)

**Say:** "Everything we just did is in an append-only event journal you can hit with read-only SQL. No magic, no hidden state — the whole demo is auditable after the fact."

**Cumulative: 4:00**

---

## Close (OLD — superseded) — BENE 2.0 vision (4:00 → 5:00, spoken, no commands)

> ⚠️ **SUPERSEDED — see "UPDATE 2026-06-11 (evening)" at the end of this file: 0.2.0 shipped, the kernel is running code. Replace this spoken close with the `uv run bene demo --no-ui` beat + 30s talking point — that new beat REPLACES this 4:00 → 5:00 slot.**

> ~~Label it honestly: **"This next part is designed, not shipped — phases 4–9 are pending. I'm showing you the design docs, not running code."**~~ *(superseded — the kernel shipped; see UPDATE below)*

"What you just saw is 0.2.0 — and the 2.0 kernel shipped last night. Yesterday I finished the 2.0 redesign, and the process is the part I'd bring to an EM role:

- **Self-critique with receipts.** `docs/research/GAP-AUDIT.md` documents 14 shortcomings in KAOS — my own sibling framework — and 13 in BENE itself, each with verbatim command-level evidence, verified against source, not docs.
- **Research-grounded.** `docs/research/SYNTHESIS.md` mines ~100 KB entries down to 48 citations, each mapped to a specific subsystem. `docs/design/DESIGN-RATIONALE.md` argues all 10 key decisions three ways — science, compression, engineering — and records every tension with its resolution.
- **The design itself** (`docs/design/BENE2-DESIGN.md`, kernel DDL in `KERNEL-SPEC.md`): the thesis is *everything is an engram*. Three headliners:
  - an **engram compression ladder** — tier 0 raw trace → episodic → semantic → procedural → strategic, every tier provenance-linked, so you can always ask 'which traces does this skill compress, and did they pass eval?';
  - a **kill-gated breeding program** — promotion of an evolved harness requires an ACCEPT verdict from a process-isolated verifier; `PromotionBlocked` is a kernel exception, because un-gated evolution reward-hacks;
  - a **trust ledger plus an enforced L0–L4 autonomy ladder** — agent reputation computed from four deterministic signals (verification coverage, audit completeness, checkpoint discipline, outcome reliability), and autonomy is earned, not configured.

The fifth pillar is the DevEx thesis: **engineers adopt agent tooling only when they trust it — so make every claim checkable.** That's what I'd bring to Apple's developer tools: not just agents that act, but agents whose every action your engineers can verify."

**Total: 5:00**

---

## Appendix — replay cheatsheet

```bash
cd /home/admin/gh/bene-main
export BENE_DB=/tmp/bene-demo-$$/bene.db; mkdir -p "${BENE_DB%/*}"
uv run bene --version
uv run bene init
AID=$(uv run python -c "from bene import Bene; b=Bene('$BENE_DB'); a=b.spawn('scout'); b.write(a,'/notes/plan.md',b'Step 1: face the fear.\n'); print(a)")
uv run bene ls
CP1=$(uv run bene checkpoint $AID --label before-refactor | python3 -c "import sys,json; print(json.load(sys.stdin)['checkpoint_id'])")
uv run python -c "from bene import Bene; b=Bene('$BENE_DB'); b.write('$AID','/notes/plan.md',b'Step 1: face the fear.\nStep 2: let it pass through.\n'); b.write('$AID','/src/refactor.py',b'def helper():\n    return 42\n')"
CP2=$(uv run bene checkpoint $AID --label after-refactor | python3 -c "import sys,json; print(json.load(sys.stdin)['checkpoint_id'])")
uv run bene diff $AID --from $CP1 --to $CP2
uv run bene restore $AID --checkpoint $CP1
uv run bene read $AID /notes/plan.md
uv run bene memory write $AID "Flaky test root cause: NTP drift on runner pool B skews TLS cert validation" -t insight -k ntp-drift
uv run bene memory search "flaky tls"
uv run bene skills save -n triage_flaky_test -d "Triage a flaky CI test by separating infra noise from product bugs" -t "Given failing test {test_name}, check runner clock skew, then rerun {retries} times to classify flake vs bug." --tags triage,ci -a $AID
uv run bene skills search "flaky triage"
uv run bene mh --help
uv run bene logs $AID --tail 3
uv run bene query "SELECT event_type, COUNT(*) AS n FROM events GROUP BY event_type ORDER BY n DESC"
rm -rf "${BENE_DB%/*}"   # cleanup
```


---

## UPDATE 2026-06-11 (evening) — BENE 0.2.0 SHIPPED: the 2.0 close is now LIVE

The "designed, build in flight" close is obsolete in the best way: **the kernel
shipped the same day** (v0.2.0, 699 tests passing post-Round-3). The strongest possible
demo beat now exists — one command, keyless, fresh directory, ~0.3s:

**Timing: this beat REPLACES the old Close (the 4:00 → 5:00 slot).** Run
`bene demo --no-ui` (~5s incl. typing; the command itself completes in ~0.3s)
+ the 30s talking point ≈ 0:40 — total stays under 5:00.

```bash
uv run bene demo --no-ui
```

Real output (executed 2026-06-11):

```text
BENE 2.0 story  /tmp/bene-demo-hyciazdx/story.db
  engrams      3 turns -> 1 episode (01KTV5KC…) — the compression ladder
  breeding     2 offline generations -> best quality 0.67 (frontier 5)
  kill gates   probe ACCEPT -> promotion ALLOWED (without it: PromotionBlocked)
  context OS   pollution score 0.0 — clean run, no recovery needed
  autonomy     L2 agent denied L4 'evolve.promote' — denial recorded as trust 
engram
  trust        composite 1.0 (1 denial on record) — computed, never declared
  senses       manifest generated from live db (1 capabilities)
story complete in 0.3s — 12 engrams, 4 experiment runs.
  inspect: bene experiments ls --db /tmp/bene-demo-hyciazdx/story.db · bene 
trust 01KTV5KCPSYP2EERN33JRZBNAC --db /tmp/bene-demo-hyciazdx/story.db
```

Talking point (30s): "Every pillar of the redesign is now running code:
the engram compression ladder, an offline breeding round, a falsifiable probe
whose ACCEPT verdict gates promotion, the autonomy ladder denying an L2 agent
an L4 capability — with the denial feeding a computed trust score. The claims
audit (docs/design/CLAIMS-AUDIT.md) marks every design claim implemented-or-
planned with test references — that is the honesty discipline I'd bring to an
AI tooling org."

If asked "what's still planned": skill-decay policy, nightly consolidation
scheduler, runner wiring for ContextOS/loop-guards, entropy-routed retrieval —
all marked in CLAIMS-AUDIT.md. Nothing in this demo is vapor.
