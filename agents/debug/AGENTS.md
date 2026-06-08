# agents/debug — agentdex-cli (post-M2 uv workspace)

> Populated 2026-06-08 (Phase 4 M2 fix-S2). Failure modes + log locations from Phase 1-4 live learning.

## Failure modes seen in the wild

1. **Stale GITHUB_TOKEN inherited by Bash tool.** Non-interactive bash spawned by Claude Code Bash tool inherits OLD token from launcher shell. ~/.bashrc op-deferred-fetch only takes effect for interactive shells. Symptom: gh returns HTTP 401. Fix: inline export GITHUB_TOKEN=$(timeout 5 op read op://openclaw/gh-pat-europa-admin-no-delete/credential 2>/dev/null) before gh call. See memory feedback-github-token-deferred-fetch.md.

2. **GH007 email-privacy push-block.** Commits w/ etang@qumulo.com rejected. Fix: noreply 3278807+EdwardTang@users.noreply.github.com via git -c user.email=...; numeric id via gh api users/EdwardTang --jq .id. See memory feedback-git-email-noreply.md.

3. **uv sync does NOT install workspace members by default.** First sync needs uv sync --all-packages. Subsequent incrementals fine.

4. **git mv fails on empty __pycache__/.** Fix: find <src> -name __pycache__ -exec rm -rf {} + before git mv.

5. **git subtree add requires clean working tree.** Commit interim BEFORE subtree add.

6. **Hermes gateway PID-file race in ensure_gateway().** Default timeout 30s. Increase for slow disks via gateway timeout= arg.

7. **Langfuse SDK absent + LANGFUSE_PUBLIC_KEY set.** agentdex_observe.init_langfuse returns False; disabled_reason() reports import error. Fix: uv pip install langfuse>=4.7,<5.0.

## Log locations

| Component | Path |
|---|---|
| Hermes gateway | ~/.hermes/profiles/<profile>/gateway.log |
| Hermes gateway PID | ~/.hermes/profiles/<profile>/gateway.pid |
| KAOS sqlite | kaos.db at repo root (post-M5) OR ~/.kaos/kaos.db |
| Expedition artifacts | expeditions/<id>/{task_card.yaml, result_card_<baseline>.yaml, pareto_verdict.yaml, evolution_card.yaml, trace/<baseline>_full_trace.jsonl} |
| Langfuse self-host | http://localhost:3000 |
| pytest output | /tmp/agentdex-cli-test.log (via tools/agent_senses/run_tests.sh) |

## Sense tools (post-M2 paths)

```bash
./packages/agentdex_cli/src/agentdex_cli/tools/agent_senses/run_tests.sh
./packages/agentdex_cli/src/agentdex_cli/tools/agent_senses/peek_metrics.sh
./packages/agentdex_cli/src/agentdex_cli/tools/agent_senses/tail_logs.sh <area>
```

## Doom-loop guard (G4 LangChain ep4)

If you edit the same file > 5 times in one session AND tests still fail — STOP. Re-read IDEAL_EXPERIENCE.md + escalate.

## R3 spike outcome debugging

```bash
uv run python -c "
import agentdex_observe as obs
obs._initialized = False
obs._client = None
ok = obs.init_langfuse()
print("Langfuse live:", ok)
print("disabled reason:", obs.disabled_reason())
print("current_trace_url:", obs.current_trace_url())
"
```

If disabled reason reports SDK import failure: uv pip install --reinstall langfuse>=4.7,<5.0.
If env unset: export LANGFUSE_PUBLIC_KEY=pk-lf-...; export LANGFUSE_SECRET_KEY=sk-lf-...; export LANGFUSE_HOST=http://localhost:3000.
If env set + live but headers empty: check Langfuse SDK v4 get_current_trace_id() API surface.
