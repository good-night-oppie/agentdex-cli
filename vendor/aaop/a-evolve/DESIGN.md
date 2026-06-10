# A-EVOLVE-V2 Architecture Design

## Core Principle

**The workspace IS the interface.** The agent reads from it, the evolver writes to it. They never talk to each other directly. Any agent that can load state from a directory can be evolved.

```
┌──────────────────────────────────────────────────────────────┐
│                     EVOLUTION LOOP                            │
│                                                              │
│   ┌─────────┐    ┌───────────┐    ┌──────────┐              │
│   │  Agent   │───▶│ Benchmark │───▶│ Observer │              │
│   │ (solve)  │    │  (eval)   │    │(collect) │              │
│   └────▲─────┘    └───────────┘    └────┬─────┘              │
│        │                                │                    │
│   reads from                      writes to                  │
│        │                                │                    │
│   ┌────┴────────────────────────────────▼─────┐              │
│   │              WORKSPACE (FS)               │              │
│   │  prompts/ skills/ tools/ memory/ evolution│              │
│   └────▲──────────────────────────────────────┘              │
│        │                                                     │
│   writes to                                                  │
│        │                                                     │
│   ┌────┴─────┐    ┌──────────┐    ┌──────────┐              │
│   │ Evolver  │◀───│  Obs Logs│◀───│ Git (VC) │              │
│   │(mutate)  │    │ (JSONL)  │    │(rollback)│              │
│   └──────────┘    └──────────┘    └──────────┘              │
└──────────────────────────────────────────────────────────────┘
```

## Separation of Concerns

Three independently developable components connected only through the workspace contract:

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   DATA + EVAL   │   │  EVOLVE ALGO    │   │   AGENT IMPL    │
│                 │   │                 │   │                 │
│ • Benchmark     │   │ • GuidedSynth   │   │ • SweAgent      │
│ • Task loader   │   │ • CoEvolve      │   │ • SwarmSolver   │
│ • Evaluator     │   │ • SwarmEvolve   │   │ • GraphSolver   │
│ • Docker eval   │   │ • (any new algo)│   │ • (any new agent│
│                 │   │                 │   │                 │
│ Provides:       │   │ Provides:       │   │ Provides:       │
│  get_tasks()    │   │  evolve()       │   │  solve()        │
│  evaluate()     │   │  step()         │   │                 │
└────────┬────────┘   └────────┬────────┘   └────────┬────────┘
         │                     │                     │
         │          ┌──────────▼──────────┐          │
         │          │                     │          │
         └─────────▶│     WORKSPACE       │◀─────────┘
                    │                     │
                    │  prompts/system.md  │
                    │  skills/*/SKILL.md  │
                    │  tools/registry.yaml│
                    │  memory/*.jsonl     │
                    │  evolution/         │
                    │  manifest.yaml      │
                    └─────────────────────┘
```

## Workspace File System Contract

```
seed_workspaces/swe/               ← copied to logs/<exp>/workspace/ at start
│
├── manifest.yaml                  ← agent entrypoint + evolvable layers
│     agent.entrypoint: agent_evolve.agents.swe.agent.SweAgent
│     evolvable_layers: [prompts, skills, memory]
│
├── prompts/
│   ├── system.md                  ← base system prompt (agent reads)
│   └── fragments/                 ← evolved prompt fragments (evolver writes)
│       ├── check_edge_cases
│       └── verify_before_after
│
├── skills/
│   └── verify_before_after_edit/
│       └── SKILL.md               ← YAML frontmatter (name, description) + body
│           ---
│           name: verify_before_after_edit
│           description: TRIGGER when making any code fix...
│           ---
│           ## Verification Methodology...
│
├── tools/
│   ├── registry.yaml              ← tool manifest [{name, file}]
│   ├── bash.py                    ← @tool decorated functions
│   ├── text_editor.py
│   └── submit.py
│
└── memory/
    └── episodic.jsonl             ← append-only memory entries
```

## Type Flow

```
Benchmark                Agent                  Evolver
   │                       │                      │
   │  get_tasks()          │                      │
   ├──────────────────▶ Task ──▶ solve() ──▶ Trajectory
   │                    │  id        │          │  output (patch)
   │                    │  input     │          │  steps (trace)
   │                    │  metadata  │          │
   │                    │            │          │
   │  evaluate()        │            │          │
   ├──────────────────▶ Feedback ◀──┘          │
   │                    │  success              │
   │                    │  score                │
   │                    │  detail               │
   │                    │                       │
   │                    ▼                       │
   │              Observation ─────────────────▶│  evolve()
   │               │  task                      │    │
   │               │  trajectory                │    │  reads obs logs
   │               │  feedback                  │    │  mutates workspace
   │                                            │    │  writes skills/prompts
   │                                            │    ▼
   │                                         Workspace (FS)
```

## BaseAgent → Concrete Agent

```
BaseAgent (protocol/base_agent.py)
│
│  Provides:
│  ├── __init__(workspace_dir)     ← loads workspace
│  ├── reload_from_fs()            ← reads prompt, skills, memories
│  ├── export_to_fs()              ← flushes memory buffer
│  ├── workspace: AgentWorkspace   ← FS access
│  ├── system_prompt: str          ← loaded from prompts/system.md
│  ├── skills: list[SkillMeta]     ← loaded from skills/*/SKILL.md
│  └── memories: list[dict]        ← loaded from memory/*.jsonl
│
│  Abstract:
│  └── solve(task: Task) -> Trajectory
│
├── SweAgent (agents/swe/agent.py)
│   │  solve():
│   │    1. Pull Docker image
│   │    2. Start container
│   │    3. Load tools from workspace (bash, text_editor, submit)
│   │    4. Build system prompt (base + verify + efficiency + skills)
│   │    5. Build user prompt (issue + memory)
│   │    6. Run strands Agent loop
│   │    7. Extract patch
│   │    8. Propose skill (for evolver)
│   │    9. Return Trajectory
│   │
│   └── _build_system_prompt():
│         parts = [
│           system.md,              ← from workspace
│           "## Verify Your Fix",   ← hardcoded
│           "## Efficiency Rules",  ← if efficiency_prompt
│           "## Skills",            ← from workspace skills
│           fragments,              ← from workspace fragments
│         ]
│
├── SwarmSweAgent (agents/swe/swarm_solver.py)    ← swe-mas-evolver branch
│   └── solve(): explorer → editor → tester via strands Swarm
│
└── GraphSweAgent (agents/swe/graph_solver.py)    ← swe-mas-evolver branch
    └── solve(): parallel explorers → synthesizer → editor → tester via Graph
```

## Evolution Algorithms

```
EvolutionEngine (engine/base.py)
│
│  Interface:
│  └── step(workspace, observations, history, trial) -> StepResult
│
├── GuidedSynthesisEngine (algorithms/guided_synth/)
│   │  The V23g-V33g single-agent evolver
│   │
│   │  step():
│   │    Phase 1: Write minimal memory (optional)
│   │    Phase 2: Parse solver proposals (TYPE/NAME/DESCRIPTION/CONTENT)
│   │    Phase 3: Curate via LLM (ACCEPT/MERGE/SKIP)
│   │    Phase 4: Write skills to workspace
│   │
│   │  Curator prompts:
│   │    GUIDED_SYNTHESIS_PROMPT     ← general skills
│   │    VERIFICATION_CURATOR_PROMPT ← verification-only skills
│   │
│   └── _execute_curation():
│         ACCEPT → workspace.write_skill(name, content)
│         MERGE  → workspace.write_skill(target, merged_content)
│         SKIP   → log and ignore
│
├── CoEvolutionEngine (algorithms/co_evolve/)     ← swe-mas-evolver
│   │  Extends GuidedSynth with:
│   │    - Dual fragment pools (solver + verifier)
│   │    - Pattern triage (A/B/C/D from interaction dynamics)
│   │
│   └── Pools:
│         workspace.write_fragment(name, content, pool="fragments")
│         workspace.write_fragment(name, content, pool="verifier_fragments")
│
└── SwarmEvolutionEngine (algorithms/swarm_evolve/) ← swe-mas-evolver
    │  Manager that evolves per-agent prompts
    │
    └── Pools:
          workspace.write_fragment(name, content, pool="explorer_fragments")
          workspace.write_fragment(name, content, pool="editor_fragments")
          workspace.write_fragment(name, content, pool="tester_fragments")
```

## Evolution Cycle (Sequential Runner)

```
evolve_sequential.py

for batch_idx in range(n_batches):
    │
    ├── 1. SOLVE (parallel)
    │   ┌──────────────────────────────────┐
    │   │  ProcessPoolExecutor(parallel=N) │
    │   │                                  │
    │   │  task_1 ──▶ solve_one_task() ──▶ result_1
    │   │  task_2 ──▶ solve_one_task() ──▶ result_2
    │   │  ...                                ...
    │   │  task_N ──▶ solve_one_task() ──▶ result_N
    │   │                                  │
    │   │  Each process:                   │
    │   │    Agent(workspace) → solve(task) │
    │   │    → Benchmark.evaluate()        │
    │   │    → {patch, score, proposal}    │
    │   └──────────────────────────────────┘
    │
    ├── 2. EVALUATE
    │   SWE-bench Docker eval: apply patch → run tests → PASS/FAIL
    │
    ├── 3. OBSERVE
    │   Observer.collect([Observation(task, trajectory, feedback)])
    │   → evolution/observations/batch_XXXX.jsonl
    │
    ├── 4. EVOLVE (if --solver-proposes)
    │   Evolver.evolve(workspace, observations)
    │   → Curate proposals → Write skills/fragments
    │   → Git commit + tag
    │
    └── 5. RELOAD
        Agent.reload_from_fs()
        → Next batch uses evolved workspace
```

## Pluggability

Any component can be swapped independently:

```
WANT TO...                    CHANGE ONLY...
─────────────────────────────────────────────
Add new agent                 agents/new_agent.py + manifest.yaml
Add new benchmark             benchmarks/new_bench/ + get_tasks/evaluate
Add new evolution algo        algorithms/new_algo/engine.py
Add new tool                  seed_workspaces/swe/tools/ + registry.yaml
Add new LLM backend           llm/new_provider.py
Change what's evolvable       manifest.yaml: evolvable_layers
```

The workspace is the universal adapter — as long as your agent reads `system.md`, `skills/`, `tools/`, and `memory/`, it can be evolved by any algorithm.

## Key Design Decisions

1. **Workspace as FS contract** — not an API, not a database. Plain files that can be git-versioned, copied, diffed, and debugged with `cat`.

2. **Evolver mutates workspace, not agent** — the evolver never touches agent code. It writes files. The agent picks them up on `reload_from_fs()`.

3. **Skills as lazy-loaded YAML+Markdown** — name + description in prompt (cheap), full body via `read_skill` tool (on demand). Descriptions are the real intervention; bodies are rarely read.

4. **Memory as append-only JSONL** — simple, bounded, no complex indexing. Just "I tried X, got score Y" for retry scenarios.

5. **Git versioning for rollback** — every evolution cycle is a commit. Bad mutation? `git reset --hard`. Full audit trail.

6. **ProcessPoolExecutor for parallel solve** — each task gets its own process with a copy of the workspace. No shared state during a batch.

7. **Benchmark provides both data AND eval** — no separate test harness. The benchmark knows how to load tasks and how to grade solutions.
