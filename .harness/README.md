# `.harness/` — corpus-query + SessionStart hook surface

> Tiny PR #5 of the autonomous-pipeline mirror (2026-06-09). Mirrors the
> `.harness/` convention used by `~/gh/eddie-agi-kb/` (symlink to
> `~/gh/harness-engineering/`).

## What lives here

| File | Purpose | Source / drift policy |
|---|---|---|
| `CORPUS_QUERY_KEYWORDS` | Seed keywords for the SessionStart corpus query against the 30-video harness-engineering proofread corpus + eddie-agi-kb concepts | Created by upstream workflow `w2we4t2ef`; re-diff quarterly |

## How the hook fires

The SessionStart hook is wired user-global in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      { "matcher": "*",
        "hooks": [
          { "type": "command",
            "command": "/home/admin/gh/harness-engineering/scripts/sessionstart_corpus_query.sh" }
        ]
      }
    ]
  }
}
```

The upstream script reads `$CWD/.harness/CORPUS_QUERY_KEYWORDS` (precedence
order: CLI args → this file → auto-derived from $CWD basename + top-level
dirs + CLAUDE.md H1/H2). It writes a 5-section corpus query report to
`/tmp/sessionstart-corpus-query-<cwd-slug>-<date>.md` and a 5-line STDOUT
summary. Always exits 0 — never blocks a session start.

Doctrine anchor: G14 ep29 [29-0007] — "一個理想的編程agent到底應該怎麼工作"
(an ideal coding agent must first be DEFINED before it can be approached).
The session-start query is the agent loading its own ideal-experience anchor
before the first action.

## Drift policy (quarterly re-diff)

Per the harness-engineering propagation pattern (each mirrored file declares
source SHA / repo / copy date):

1. Every quarter, compare `CORPUS_QUERY_KEYWORDS` against the upstream
   shape (`../eddie-agi-kb/.harness/CORPUS_QUERY_KEYWORDS` if present, or
   the schema in `sessionstart_corpus_query.sh`).
2. Adjust adx-cli's keyword set to reflect new domain language (Hermes
   plugin terms, KAOS substrate vocabulary, Three Cards revisions).
3. Log the diff in `sweeps/<date>-keyword-drift.md`.

## Why this is NOT a copy of `sessionstart_corpus_query.sh`

Per the harness-engineering "shared-rules" pattern (target: versioned
`~/.claude/shared-rules/` with SkillClaw-pinned per-consumer versions),
adx-cli does NOT vendor a local copy of the script. The hook fires the
upstream script directly. This file is the per-project SEED, not a
replicated runner.

## Related

- `cron/expedition_smoke.sh` — daily smoke gate (mirror of upstream
  `cron/daily_ingest.sh` shape)
- `cron/weekly_harness_audit.sh` — weekly doctrine-vs-filesystem audit
  (mirror of `scripts/weekly_meta_audit.sh` shape)
- `tools/agent_senses/` — G2 ep4 read-back loop scripts
- `scripts/sync_toc.sh` — CLAUDE.md TOC sync (ported from upstream)
