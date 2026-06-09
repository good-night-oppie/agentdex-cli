# Bridge smoke-probe fixtures (G13 ground-truth)

Referenced by `EVAL.md` row "Subscription-CLI bridge smoke probe passes at
session start". Each baseline ships ONE recorded fixture against which a
bridge handshake can be compared deterministically — the M5 + post-M5 gate
that detects the failure mode described in `IDEAL_EXPERIENCE.md` §Failure
modes #5 ("Subscription-CLI drift").

## Why these files exist (now empty)

The harness-praxis tracer pass (2026-06-09) surfaced that `EVAL.md:22` named
this directory but the directory did not exist. Per harness-praxis §G13
"eval signal", a ghost criterion is worse than no criterion: it implies a
gate that nothing actually enforces. This README + the schemas below convert
"ghost criterion" into "bounded debt with a typed shape" so any contributor
landing the live fixtures has no design freedom to drift.

## File layout (one fixture per baseline)

```
tests/fixtures/bridges/
├── README.md                      # this file
├── claude_smoke.json              # P-1 — record + ship
├── codex_smoke.json               # P-1 — record + ship
└── manus_smoke.json               # P-2 — codex-web fallback variant
```

## Schema (per file)

```json
{
  "bridge": "claude|codex|manus",
  "binary_version": "string",       // e.g. "claude 1.0.84 (Claude Code)"
  "captured_at": "2026-06-09T00:00:00Z",
  "captured_with": "tools/agent_senses/capture_bridge_smoke.sh <bridge>",
  "handshake": {
    "argv": ["claude", "-p", "...", "--output-format", "stream-json"],
    "ms_until_init_frame": 2840,
    "stdout_frames": [
      {"type": "system", "subtype": "init", "fields": ["session_id", "..."]}
    ]
  },
  "one_turn_probe": {
    "prompt": "Reply with the literal string OK and nothing else.",
    "expected_text_regex": "^\\s*OK\\s*$",
    "max_ms": 12000,
    "max_cost_usd": 0.01
  },
  "drift_detector": {
    "fields_required_in_result_frame": [
      "session_id",
      "total_cost_usd",
      "usage.input_tokens",
      "usage.output_tokens"
    ],
    "fields_required_in_codex_turn_completed": [
      "turnId",
      "tokenUsage.inputTokens",
      "tokenUsage.outputTokens"
    ]
  }
}
```

## Capture script (planned, M6+)

`tools/agent_senses/capture_bridge_smoke.sh <bridge>` will:

1. Spawn the live bridge via the same code path as `adx bridge probe`.
2. Record the first 5 stdout frames + the one-turn probe result.
3. Strip session-specific UUIDs / timestamps (replace with `<UUID>` /
   `<ISO>` placeholders).
4. Write the JSON above.

The capture is a one-time hand-blessed artifact; subsequent runs only verify
the live bridge's handshake + result frame still match the schema fields
listed in `drift_detector`.

## Why this is NOT a fixture-replay mock

The smoke fixture asserts *shape*, not *content*. A captured Claude Code
session is NOT replayed deterministically; the fixture only asserts the
handshake fields + result-frame field-set the bridge code reads. This keeps
the gate from being broken by routine upstream UX/wording changes while
still detecting structural protocol drift.

## Status

- 2026-06-09 — directory + schema scaffolded by the harness-praxis tracer
  follow-up (MF4 gap). Live captures land with the M6+ live-pool work.
