# Terminal-Bench 2.0 Experiment Scripts

Two bash scripts for running Terminal-Bench 2.0 experiments. Both use `batch_evolve_terminal.py` with the ReAct solver and Opus 4.6.

## Scripts

### `run_baseline.sh` — No Evolution,

Runs tasks without evolution (vanilla prompt only). This is the pure baseline to measure the model's raw capability.

```bash
# Full run (all tasks, 6 workers)
bash examples/tb_examples/run_baseline.sh Mar25_baseline 
# Quick test (1 task)
bash examples/tb_examples/run_baseline.sh Mar25_test --limit 1

# Custom workers
bash examples/tb_examples/run_baseline.sh Mar25_baseline --workers 8 

# Background
nohup bash examples/tb_examples/run_baseline.sh Mar25_baseline &
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--limit N` | all | Number of tasks to run |
| `--workers N` | 6 | Parallel workers |
| `--exclude list` | none | Comma-separated task names to skip if necessary |

**Output:**
- Logs: `logs/baseline_<RUN_NAME>/`
- Results: `logs/baseline_<RUN_NAME>/results.jsonl`
- Workspace: `/tmp/baseline_<RUN_NAME>/`

### `run_evolution.sh` — Phase 1 (Evolve) + Phase 2 (Evaluate)

Two-phase experiment using all 5 seed skills. Phase 1 evolves on N tasks, Phase 2 evaluates remaining tasks with the evolved workspace.

Evolution settings: `--trajectory-only --skills-only --protect-skills` (evolver can only ADD new skills, not modify existing ones).

```bash
# Quick 1+1 test
bash examples/tb_examples/run_evolution.sh Mar25_test \
  --evolve-limit 1 --eval-limit 1 --batch-size 1


# Full run 
bash examples/tb_examples/run_evolution.sh Mar25_v1 
# Full run(If needed, you can exclude some tasks) 
bash examples/tb_examples/run_evolution.sh Mar25_v1 \
  --exclude extract-moves-from-video,qemu-startup,build-pov-ray,db-wal-recovery

# Custom split (10 evolve + 20 eval, batch-size 5)
bash examples/tb_examples/run_evolution.sh Mar25_v2 \
  --evolve-limit 10 --eval-limit 20 --batch-size 5 

# Background with 8 workers
nohup bash examples/tb_examples/run_evolution.sh Mar25_v1 --workers 8 &
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--evolve-limit N` | 20 | Number of tasks for Phase 1 (evolution) |
| `--eval-limit N` | all remaining | Number of additional tasks for Phase 2 (evaluation) |
| `--batch-size N` | 5 | Tasks per batch before each evolution cycle |
| `--max-skills N` | 6 | Maximum total skills allowed |
| `--workers N` | 6 | Parallel workers |
| `--exclude list` | none | Comma-separated task names to skip |

**Output:**
- Logs: `logs/evolve_<RUN_NAME>/`
- Results: `logs/evolve_<RUN_NAME>/results.jsonl`
- Workspace: `evolution_workdir/evolve_<RUN_NAME>/`

## How It Works

### Baseline Flow

```
seed_workspaces/terminal/ (5 skills)
    -> copy to /tmp, remove ALL skills (--no-skills)
    -> solve tasks with --no-evolve
    -> report results
```

### Evolution Flow

```
Phase 1 (evolve):
    seed_workspaces/terminal/ (5 skills)
        -> copy to evolution_workdir/
        -> solve batch of tasks
        -> evolver analyzes trajectories (LLM judge scores each task)
        -> evolver creates NEW skills (existing skills protected)
        -> repeat for evolve-limit tasks

Phase 2 (evaluate):
    evolution_workdir/ (5+ skills)
        -> solve remaining tasks with --no-evolve
        -> resume skips Phase 1 tasks automatically
        -> report combined Phase 1 + Phase 2 results
```

### Evolution Constraints

- `--trajectory-only`: Evolver sees only agent trajectories, no pass/fail labels
- `--skills-only`: Evolver can only modify skills (not prompts, memory, or tools)
- `--protect-skills`: Evolver cannot modify/delete existing skills, only add new ones
- `--max-skills`: Budget cap on total number of skills

## Quick Verification

```bash
# Test baseline (1 task, ~1-10 min)
bash examples/tb_examples/run_baseline.sh test --limit 1 --workers 1

# Test evolution (1+1 tasks, ~5-15 min)
bash examples/tb_examples/run_evolution.sh test \
  --evolve-limit 1 --eval-limit 1 --batch-size 1 --workers 1
```

## Pipeline Flags Reference

Key flags for `batch_evolve_terminal.py`:

| Flag | Description |
|------|-------------|
| `--no-evolve` | Skip evolution (solve only) |
| `--no-skills` | Remove all skills from workspace (vanilla baseline) |
| `--solver react` | Use ReAct solver (default) |
| `--trajectory-only` | Evolver sees only trajectories |
| `--skills-only` | Evolver can only modify skills |
| `--protect-skills` | Evolver can only add, not modify skills |
| `--max-skills N` | Skill budget cap |
| `--tasks t1,t2` | Run specific tasks only |
| `--exclude t1,t2` | Skip specific tasks |
| `--limit N` | Max number of tasks |
| `--workers N` | Parallel workers |
