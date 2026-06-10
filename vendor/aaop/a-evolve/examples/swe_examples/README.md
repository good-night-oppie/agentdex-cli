# SWE-bench Scripts

Two scripts for running SWE-bench experiments. Always use `uv run` for Python commands.

## 1. Baseline — `solve_all.py`

Solve all tasks in parallel without evolution. No workspace, no skill evolution.

```bash
# SWE-bench Verified (500 tasks), Opus 4.6, 16 parallel workers
uv run python examples/swe_examples/solve_all.py \
  --dataset princeton-nlp/SWE-bench_Verified \
  --model-id us.anthropic.claude-opus-4-6-v1 \
  --workers 16 \
  --max-turns 140 \
  --output-dir logs/baseline \
  --limit 500

# Mini (50 tasks) for quick testing
uv run python examples/swe_examples/solve_all.py \
  --dataset MariusHobbhahn/swe-bench-verified-mini \
  --model-id us.anthropic.claude-opus-4-6-v1 \
  --workers 5 \
  --max-turns 140 \
  --output-dir logs/baseline-mini \
  --limit 50
```

**Key flags:**
- `--dataset` — HuggingFace dataset name
- `--model-id` — Bedrock model ID (`us.anthropic.claude-opus-4-6-v1`, `us.anthropic.claude-sonnet-4-6`, etc.)
- `--workers` — parallel task count
- `--max-turns` — max tool calls per task
- `--limit` — max tasks to solve
- `--no-eval` — skip evaluation (just produce patches)

## 2. Evolution — `evolve_sequential.py`

Solve tasks in batches with skill evolution between batches. Uses a seed workspace that evolves over time.

```bash
# v32g settings — our best config (384/500 = 76.8%)
uv run python examples/swe_examples/evolve_sequential.py \
  --dataset princeton-nlp/SWE-bench_Verified \
  --batch-size 20 --parallel 20 \
  --max-steps 140 --window-size 70 \
  --efficiency-prompt \
  --solver-proposes --verification-focus \
  --feedback none \
  --model-id us.anthropic.claude-opus-4-6-v1 \
  --seed-workspace seed_workspaces/swe \
  --output-dir logs/v32g-full \
  --limit 500

# Mini (50 tasks) for quick testing
uv run python examples/swe_examples/evolve_sequential.py \
  --dataset MariusHobbhahn/swe-bench-verified-mini \
  --batch-size 5 --parallel 5 \
  --max-steps 140 --window-size 40 \
  --efficiency-prompt \
  --solver-proposes --verification-focus \
  --feedback none \
  --model-id us.anthropic.claude-opus-4-6-v1 \
  --seed-workspace seed_workspaces/swe \
  --output-dir logs/test-mini \
  --limit 50

# No evolution (pure baseline with workspace tools)
uv run python examples/swe_examples/evolve_sequential.py \
  --dataset princeton-nlp/SWE-bench_Verified \
  --batch-size 10 --parallel 10 \
  --max-steps 140 --window-size 70 \
  --efficiency-prompt --no-evolve \
  --model-id us.anthropic.claude-opus-4-6-v1 \
  --seed-workspace seed_workspaces/swe \
  --output-dir logs/baseline-ws \
  --limit 500
```

**Key flags:**
- `--batch-size` — tasks per evolution batch
- `--parallel` — parallel workers within each batch
- `--max-steps` — max tool calls per task (140 recommended)
- `--window-size` — sliding window message count (70 recommended)
- `--efficiency-prompt` — add hypothesis-first approach constraints
- `--solver-proposes` — solver proposes skills after each task
- `--verification-focus` — propose verification skills only
- `--feedback none` — evolver doesn't see pass/fail scores
- `--no-evolve` — disable evolution (baseline with workspace tools)
- `--seed-workspace` — starting workspace directory

## Output

Both scripts produce:
```
logs/<experiment>/
  ├── patches/              # One .diff per task
  ├── conversations/        # Full conversation JSON per task
  ├── workspace/            # Evolved workspace (evolve_sequential only)
  └── results.json          # Per-task scores and metrics
```
