---
title: "Harbor CLI surface capture (M2 WU-8)"
status: active
owner: "@EdwardTang"
created: 2026-07-11
updated: 2026-07-11
type: reference
scope: .fleet-goal/evidence/M2
layer: cross-cutting
cross_cutting: true
---

# Harbor CLI surface (verbatim)

Captured from installed `harbor` after `uv tool install harbor`.

- **harbor version:** `0.18.0`

## Flag map used by `HarborCliClient`

| Need | Real flag (harbor 0.18.0) | Notes |
|------|---------------------------|-------|
| Dataset selection | `-d` / `--dataset` | e.g. `terminal-bench/terminal-bench-2` or `terminal-bench@2.0` |
| Single-task filter | `-i` / `--include-task-name` | Supports globs; **not** `--task-name` (docs drift) |
| Agent (built-in or custom import) | `-a` / `--agent` | Accepts `module.path:ClassName`; `--agent-import-path` still works but is deprecated |
| Model | `-m` / `--model` | Optional; repeatable |
| Jobs / output directory | `-o` / `--jobs-dir` | Default: relative `jobs` (not `~/.cache/harbor/jobs`) |
| Job name | `--job-name` | Defaults to timestamp; client sets a unique name per task |
| Max tasks | `-l` / `--n-tasks` | Applied after filters |

## Task listing surface

`harbor dataset list` lists **datasets in a registry**, not task ids inside a dataset.
`harbor task` has init/download/start-env/… — **no** “list tasks in dataset” subcommand.

**Documented fallback for `HarborCliClient.list_tasks`:** return the constructor-injected
`tasks` tuple; raise `ValueError` when `tasks is None`. Never invent a hardcoded fake list.

## On-disk result artifacts (official docs + TrialResult schema)

```
jobs/<job-name>/
├── config.json
├── result.json                 # JobResult (stats.cost_usd aggregate optional)
└── <trial-name>/
    ├── config.json
    ├── result.json             # TrialResult — source of truth for pass/cost
    ├── agent/…
    └── verifier/
        ├── reward.txt          # often a single float; also mirrored in result.json
        └── …
```

Pass criterion (harbor analyzer): `verifier_result.rewards.get("reward", 0) == 1.0`
Measured cost (when present): `agent_result.cost_usd` on the trial `result.json`
(else `None` → adapter declared-budget fallback, `cost_is_measured=False`).

## Background

Verbatim upstream help captures (harbor 0.18.0) — quoted reference text,
not SLA claims by this repo.

### `harbor --help`

```
                                                                                
 Usage: harbor [OPTIONS] COMMAND [ARGS]...                                      
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --version             -v                                                     │
│ --install-completion            Install completion for the current shell.    │
│ --show-completion               Show completion for the current shell, to    │
│                                 copy it or customize the installation.       │
│ --help                -h        Show this message and exit.                  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ check        Check task quality against a rubric.                            │
│ analyze      Analyze trial trajectories.                                     │
│ init         Initialize a new task or dataset.                               │
│ run          Start a job. Alias for `harbor job start`.                      │
│ exec         Compile paths into tasks and run a job.                         │
│ publish      Publish tasks and datasets to the Harbor registry.              │
│ upload       Upload job results to the Harbor platform.                      │
│ add          Add tasks or datasets to a dataset.toml.                        │
│ download     Download a task or dataset.                                     │
│ remove       Remove tasks from a dataset.toml.                               │
│ sync         Update task digests in a dataset manifest.                      │
│ view         Start web server to browse trajectory files.                    │
│ adapter      Manage adapters.                                                │
│ task         Manage tasks.                                                   │
│ dataset      Manage datasets.                                                │
│ job          Manage jobs.                                                    │
│ hub          View Harbor Hub jobs, tasks, and trials.                        │
│ trial        Manage trials.                                                  │
│ cache        Manage Harbor cache.                                            │
│ plugins      Manage job plugins.                                             │
│ auth         Manage authentication.                                          │
│ leaderboard  Manage leaderboards.                                            │
╰──────────────────────────────────────────────────────────────────────────────╯

```

### `harbor run --help`

```
                                                                                
 Usage: harbor run [OPTIONS]                                                    
                                                                                
 Start a job. Alias for `harbor job start`.                                     
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Config ─────────────────────────────────────────────────────────────────────╮
│ --config        -c      PATH  A job configuration path in yaml or json       │
│                               format. Should implement the schema of         │
│                               harbor.models.job.config:JobConfig. Allows for │
│                               more granular control over the job             │
│                               configuration.                                 │
│ --print-config                Print the resolved JobConfig JSON and exit.    │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Job Settings ───────────────────────────────────────────────────────────────╮
│ --job-name                      TEXT                  Name of the job        │
│                                                       (default: timestamp)   │
│ --jobs-dir              -o      PATH                  Directory to store job │
│                                                       results (default:      │
│                                                       jobs)                  │
│ --n-attempts            -k      INTEGER               Number of attempts per │
│                                                       trial (default: 1)     │
│ --timeout-multiplier            FLOAT                 Multiplier for task    │
│                                                       timeouts (default:     │
│                                                       1.0)                   │
│ --agent-timeout-multi…          FLOAT                 Multiplier for agent   │
│                                                       execution timeout      │
│                                                       (overrides             │
│                                                       --timeout-multiplier)  │
│ --verifier-timeout-mu…          FLOAT                 Multiplier for         │
│                                                       verifier timeout       │
│                                                       (overrides             │
│                                                       --timeout-multiplier)  │
│ --agent-setup-timeout…          FLOAT                 Multiplier for agent   │
│                                                       setup timeout          │
│                                                       (overrides             │
│                                                       --timeout-multiplier)  │
│ --environment-build-t…          FLOAT                 Multiplier for         │
│                                                       environment build      │
│                                                       timeout (overrides     │
│                                                       --timeout-multiplier)  │
│ --quiet,--silent        -q                            Suppress individual    │
│                                                       trial progress         │
│                                                       displays               │
│ --debug                                               Enable debug logging   │
│ --n-concurrent          -n      INTEGER               Number of concurrent   │
│                                                       trials to run          │
│                                                       (default: 4)           │
│ --n-concurrent-agents           INTEGER RANGE [x>=1]  Per-agent cap on       │
│                                                       concurrent agent       │
│                                                       execution phases; must │
│                                                       be no higher than      │
│                                                       --n-concurrent         │
│                                                       (default: unset)       │
│ --max-retries           -r      INTEGER               Maximum number of      │
│                                                       retry attempts         │
│                                                       (default: 0)           │
│ --retry-include                 TEXT                  Exception types to     │
│                                                       retry on. If not       │
│                                                       specified, all         │
│                                                       exceptions except      │
│                                                       those in               │
│                                                       --retry-exclude are    │
│                                                       retried (can be used   │
│                                                       multiple times)        │
│ --retry-exclude                 TEXT                  Exception types to NOT │
│                                                       retry on (can be used  │
│                                                       multiple times)        │
│ --yes                   -y                            Auto-confirm prompts,  │
│                                                       including host         │
│                                                       environment access and │
│                                                       sharing with           │
│                                                       organizations you are  │
│                                                       not a member of.       │
│ --env-file                      PATH                  Path to a .env file to │
│                                                       load into environment. │
│ --install-only                                        Run agent              │
│                                                       setup/install only,    │
│                                                       then exit. Skips the   │
│                                                       agent run and implies  │
│                                                       --disable-verificatio… │
│                                                       Fast install           │
│                                                       compatibility check.   │
│ --artifact                      TEXT                  Environment path to    │
│                                                       download as an         │
│                                                       artifact after the     │
│                                                       trial (can be used     │
│                                                       multiple times)        │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Agent ──────────────────────────────────────────────────────────────────────╮
│ --agent               -a      [aider|antigravity-cli  Agent to run, or a     │
│                               |claude-code|cline-cli  custom agent import    │
│                               |codex|computer-1|copi  path                   │
│                               lot-cli|cursor-cli|dev  (module.path:ClassNam… │
│                               in|dspy-rlm|eve|gemini  Also accepts an ACP    │
│                               -cli|goose|hermes|kimi  registry shorthand     │
│                               -cli|langgraph|mimo|mi  (e.g.                  │
│                               ni-swe-agent|nemo-agen  acp:opencode@1.3.9).   │
│                               t|nop|openclaw|opencod                         │
│                               e|openhands|openhands-                         │
│                               sdk|oracle|pi|qwen-cod                         │
│                               er|rovodev-cli|swe-age                         │
│                               nt|terminus|terminus-1                         │
│                               |terminus-2|trae-agent                         │
│                               |acp:<agent>]                                  │
│ --model               -m      TEXT                    Model name for the     │
│                                                       agent (can be used     │
│                                                       multiple times)        │
│ --ak,--agent-kwarg            TEXT                    Additional agent kwarg │
│                                                       in the format          │
│                                                       'key=value'. You can   │
│                                                       view available kwargs  │
│                                                       by looking at the      │
│                                                       agent's `__init__`     │
│                                                       method. Can be set     │
│                                                       multiple times to set  │
│                                                       multiple kwargs.       │
│ --allow-agent-host            TEXT                    Run-specific hostname  │
│                                                       or IP address/CIDR     │
│                                                       merged into the agent  │
│                                                       phase allowlist during │
│                                                       agent.run() only. Can  │
│                                                       be used multiple       │
│                                                       times.                 │
│ --ae,--agent-env              TEXT                    Environment variable   │
│                                                       to pass to the agent   │
│                                                       in KEY=VALUE format.   │
│                                                       Can be used multiple   │
│                                                       times. Example: --ae   │
│                                                       AWS_REGION=us-east-1   │
│ --agent-include-logs          TEXT                    Glob pattern of files  │
│                                                       to download from the   │
│                                                       agent logs directory,  │
│                                                       relative to it. Can be │
│                                                       used multiple times.   │
│ --agent-exclude-logs          TEXT                    Glob pattern of files  │
│                                                       to skip when           │
│                                                       downloading the agent  │
│                                                       logs directory,        │
│                                                       relative to it.        │
│                                                       Applied after          │
│                                                       includes. Can be used  │
│                                                       multiple times.        │
│ --mcp-config                  PATH                    Path to a Claude-style │
│                                                       .mcp.json or Harbor    │
│                                                       MCP config file. Can   │
│                                                       be used multiple       │
│                                                       times.                 │
│ --skill,--skills              TEXT                    Path or git source     │
│                                                       (org/name, URL) for    │
│                                                       skill directories. Can │
│                                                       be used multiple       │
│                                                       times.                 │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Environment ────────────────────────────────────────────────────────────────╮
│ --env              -e                     [ack|apple-conta  Environment type │
│                                           iner|beam|blaxel  (default:        │
│                                           |cua-cloud|cwsan  docker) or a     │
│                                           dbox|daytona|doc  custom           │
│                                           ker|e2b|ec2|gke|  environment      │
│                                           islo|langsmith|m  import path      │
│                                           odal|novita|open  (module.path:Cl… │
│                                           sandbox|openshif                   │
│                                           t|runloop|singul                   │
│                                           arity|tensorlake                   │
│                                           |use-computer|wa                   │
│                                           ndb]                               │
│ --allow-environm…                         TEXT              Run-specific     │
│                                                             hostname or IP   │
│                                                             address/CIDR     │
│                                                             merged into the  │
│                                                             network baseline │
│                                                             at agent env     │
│                                                             start. Can be    │
│                                                             used multiple    │
│                                                             times.           │
│ --force-build          --no-force-bui…                      Whether to force │
│                                                             rebuild the      │
│                                                             environment      │
│                                                             (default:        │
│                                                             --no-force-buil… │
│ --delete               --no-delete                          Whether to       │
│                                                             delete the       │
│                                                             environment      │
│                                                             after completion │
│                                                             (default:        │
│                                                             --delete)        │
│ --cpus                                    [auto|limit|requ  How to apply     │
│                                           est|guarantee|ig  task CPU         │
│                                           nore]             resources: auto, │
│                                                             limit, request,  │
│                                                             guarantee, or    │
│                                                             ignore.          │
│ --memory                                  [auto|limit|requ  How to apply     │
│                                           est|guarantee|ig  task memory      │
│                                           nore]             resources: auto, │
│                                                             limit, request,  │
│                                                             guarantee, or    │
│                                                             ignore.          │
│ --override-cpus                           INTEGER           Override the     │
│                                                             number of CPUs   │
│                                                             for the          │
│                                                             environment      │
│ --override-memor…                         INTEGER           Override the     │
│                                                             memory (in MB)   │
│                                                             for the          │
│                                                             environment      │
│ --override-stora…                         INTEGER           Override the     │
│                                                             storage (in MB)  │
│                                                             for the          │
│                                                             environment      │
│ --override-gpus                           INTEGER           Override the     │
│                                                             number of GPUs   │
│                                                             for the          │
│                                                             environment      │
│ --override-tpu                            TEXT              Override the TPU │
│                                                             spec for the     │
│                                                             environment in   │
│                                                             TYPE=TOPOLOGY    │
│                                                             format (e.g.     │
│                                                             'v6e=2x4'). The  │
│                                                             task allocates   │
│                                                             one TPU slice    │
│                                                             per pod, so only │
│                                                             a single spec is │
│                                                             accepted.        │
│ --mounts,--mount…                         TEXT              JSON array of    │
│                                                             volume mounts    │
│                                                             for the          │
│                                                             environment      │
│                                                             container        │
│                                                             (Docker Compose  │
│                                                             service volume   │
│                                                             format).         │
│                                                             --mounts-json is │
│                                                             a deprecated     │
│                                                             alias.           │
│ --extra-docker-c…                         PATH              Additional       │
│                                                             Docker Compose   │
│                                                             overlay file.    │
│                                                             Can be used      │
│                                                             multiple times.  │
│ --ek,--environme…                         TEXT              Environment      │
│                                                             kwarg in         │
│                                                             key=value format │
│                                                             (can be used     │
│                                                             multiple times)  │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Verifier ───────────────────────────────────────────────────────────────────╮
│ --ve,--verifier-env                              TEXT  Environment variable  │
│                                                        to pass to the        │
│                                                        verifier in KEY=VALUE │
│                                                        format. Can be used   │
│                                                        multiple times.       │
│                                                        Example: --ve         │
│                                                        OPENAI_BASE_URL=http… │
│ --verifier-include-l…                            TEXT  Glob pattern of files │
│                                                        to download from the  │
│                                                        verifier logs         │
│                                                        directory, relative   │
│                                                        to it. Can be used    │
│                                                        multiple times.       │
│ --verifier-exclude-l…                            TEXT  Glob pattern of files │
│                                                        to skip when          │
│                                                        downloading the       │
│                                                        verifier logs         │
│                                                        directory, relative   │
│                                                        to it. Applied after  │
│                                                        includes. Can be used │
│                                                        multiple times.       │
│ --verifier                                       TEXT  Custom verifier       │
│                                                        import path           │
│                                                        (module.path:ClassNa… │
│ --verifier-kwarg                                 TEXT  Additional verifier   │
│                                                        kwarg in the format   │
│                                                        'key=value'.          │
│ --disable-verificati…    --enable-verificati…          Disable task          │
│                                                        verification (skip    │
│                                                        running tests)        │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Dataset ────────────────────────────────────────────────────────────────────╮
│ --path                    -p      PATH     Path to a local task or dataset   │
│                                            directory                         │
│ --extra-instruction-path          PATH     Path to an extra instruction file │
│                                            to append to the task             │
│                                            instruction. Can be used multiple │
│                                            times.                            │
│ --task-git-url                    TEXT     Git URL for a task repository     │
│ --task-git-commit                 TEXT     Git commit ID for the task        │
│                                            (requires --task-git-url)         │
│ --dataset                 -d      TEXT     Dataset name@version (e.g.,       │
│                                            'dataset@1.0')                    │
│ --registry-url                    TEXT     Registry URL for remote dataset   │
│                                            [default: (The default harbor     │
│                                            registry.)]                       │
│ --registry-path                   PATH     Path to a registry.json file or   │
│                                            its parent directory. With        │
│                                            --repo, this is a repo-relative   │
│                                            path.                             │
│ --repo                            TEXT     Git registry to resolve datasets  │
│                                            from (e.g. 'org/name', a          │
│                                            GitHub/Hugging Face/GitLab URL,   │
│                                            optionally pinned with '@ref').   │
│ --task                    -t      TEXT     Run a single task from the        │
│                                            registry (org/name)               │
│ --include-task-name       -i      TEXT     Task name to include from dataset │
│                                            (supports glob patterns)          │
│ --exclude-task-name       -x      TEXT     Task name to exclude from dataset │
│                                            (supports glob patterns)          │
│ --n-tasks                 -l      INTEGER  Maximum number of tasks to run    │
│                                            (applied after other filters)     │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Integrations ───────────────────────────────────────────────────────────────╮
│ --plugin                   TEXT  Import path for a job plugin class          │
│                                  (module:ClassName). Repeatable.             │
│ --pk,--plugin-kwarg        TEXT  Additional plugin kwarg in the format       │
│                                  'key=value'. Can be set multiple times.     │
│                                  Requires exactly one --plugin.              │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Harbor Hub ─────────────────────────────────────────────────────────────────╮
│ --upload                           After the job finishes, upload it to      │
│                                    Harbor Hub so you can share the run via a │
│                                    link.                                     │
│ --public        --private          Visibility for the uploaded job. Requires │
│                                    --upload. No flag = private (default).    │
│ --share-org                  TEXT  Share the uploaded job with an            │
│                                    organization. Requires --upload.          │
│                                    Repeatable.                               │
│ --share-user                 TEXT  Share the uploaded job with a GitHub      │
│                                    username. Requires --upload. Repeatable.  │
╰──────────────────────────────────────────────────────────────────────────────╯

```

### `harbor dataset --help`

```
                                                                                
 Usage: harbor dataset [OPTIONS] COMMAND [ARGS]...                              
                                                                                
 Manage datasets.                                                               
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ list        List all datasets available in a registry.                       │
│ init        Initialize a new dataset directory.                              │
│ download    Download a dataset from a registry.                              │
│ visibility  Get, set, or toggle the visibility of a published dataset.       │
╰──────────────────────────────────────────────────────────────────────────────╯

```

### `harbor dataset list --help`

```
                                                                                
 Usage: harbor dataset list [OPTIONS]                                           
                                                                                
 List all datasets available in a registry.                                     
                                                                                
 By default, prints a link to the Harbor registry website. Use --legacy         
 to show the table-based listing.                                               
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --registry-url           TEXT  Registry URL for remote dataset listing       │
│                                [default: (The default legacy harbor          │
│                                registry.)]                                   │
│ --registry-path          PATH  Path to a registry.json file or its parent    │
│                                directory. With --repo, this is a             │
│                                repo-relative path.                           │
│ --repo                   TEXT  Git registry to list datasets from (e.g.      │
│                                'org/name' or a full git URL, optionally      │
│                                pinned with '@ref').                          │
│ --legacy                       Show the legacy table-based listing instead   │
│                                of the registry website link.                 │
│ --help           -h            Show this message and exit.                   │
╰──────────────────────────────────────────────────────────────────────────────╯

```

### `harbor task --help`

```
                                                                                
 Usage: harbor task [OPTIONS] COMMAND [ARGS]...                                 
                                                                                
 Manage tasks.                                                                  
                                                                                
╭─ Options ────────────────────────────────────────────────────────────────────╮
│ --help  -h        Show this message and exit.                                │
╰──────────────────────────────────────────────────────────────────────────────╯
╭─ Commands ───────────────────────────────────────────────────────────────────╮
│ init        Initialize a new task directory.                                 │
│ download    Download a task from the Harbor package registry.                │
│ start-env   Start an environment for a task.                                 │
│ update      Add or update task package info in task.toml.                    │
│ annotate    Generate README.md and description for task(s) using a Harbor    │
│             job.                                                             │
│ visibility  Set or toggle the visibility of a published task.                │
│ migrate     Migrate Terminal Bench tasks to Harbor format.                   │
╰──────────────────────────────────────────────────────────────────────────────╯

```
