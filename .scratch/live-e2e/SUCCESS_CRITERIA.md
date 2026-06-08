# Live E2E Validation — Lifecycle-Scoped Langfuse (鸭哥 Result Certainty)

NO mocked. Langfuse scoped to **Expedition lifecycle** (not always-on).

## Pipeline

1. `adx expedition --task nvidia-earnings-infographic --baselines claude,codex,manus --judge claude-haiku-4.5 --output expeditions/live-001/`
2. Pre-flight: ensure_langfuse() probes health → if down, docker compose up -d → wait healthy → init project + grab API keys
3. 3 real subscription bridges run sequentially, each turn @trace_turn into Langfuse
4. Soft Oracle anthropic_client.messages.create real call → Langfuse-instrumented
5. EvolutionCard emitted, KAOS lineage persisted
6. Langfuse stays up post-run so user can drill-down
7. `adx langfuse down` to tear down on demand

## Hard pass criteria (跟 lifecycle 走)

1. [ ] `adx langfuse up` brings up Langfuse stack (postgres+clickhouse+redis+minio+web+worker), `/api/public/health` returns 200 in <90s
2. [ ] ANTHROPIC_API_KEY exported from op vault openclaw before expedition
3. [ ] LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY persisted in ~/.adx/langfuse.env, sourced by `adx expedition`
4. [ ] `adx expedition` runs WITHOUT --mocked, 3 real CLIs invoked
5. [ ] expeditions/live-001/result_card_<agent>.yaml ×3, each with non-null langfuse_trace_id
6. [ ] expeditions/live-001/evolution_card.yaml has non-empty langfuse_trace_urls dict
7. [ ] curl http://localhost:3000/api/public/traces?limit=10 returns ≥1 trace whose name matches `expedition.*`
8. [ ] One trace has child span named `<bridge>.send` with parent_id = expedition trace_id
9. [ ] One trace has child span for Anthropic SDK judge call (auto-instrumented via agentdex_observe.anthropic_client)
10. [ ] `kaos serve` MCP server runs, `mcp__kaos__agent_ls` returns the expedition lineage agent
11. [ ] EvolutionCard.mutation_seeds ≥2 categories, all seed_provenance="structural" (honest M5 floor)

## Cost ceiling

- Anthropic API spend: 3 judge calls × ~2000 tok in × 500 tok out × $0.80/1M in + $4/1M out ≈ $0.01
- Claude subscription bridge call: uses subscription quota (not API key)
- Total expected: <$0.05
